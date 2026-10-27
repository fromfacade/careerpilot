"""One visible Greenhouse browser at a time. The window stays open for review.

Playwright calls stay on the thread that launched Chromium. Nothing in this
module clicks Submit or writes cookies to disk.
"""

from __future__ import annotations

import queue
import secrets
import threading
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright

from app.autofill.actions import decide_fill, resume_marker, reviewed_fields
from app.autofill.browser_fill import FillReport, NavigationBlocked, apply_actions, open_application
from app.autofill.mapping import AutofillPlan
from app.core.db import session_scope
from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.services import autofill_service, candidate_service, preparation_service

_LOCK = threading.Lock()
_SESSIONS: dict[str, "AutofillRun"] = {}


@dataclass
class AutofillRun:
    id: str
    preparation_id: int
    candidate_id: int
    state: str
    employer: str
    job_title: str
    apply_url: str
    message: str = ""
    plan: AutofillPlan | None = None
    result: FillReport | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    reviewed: dict = field(default_factory=dict)
    _worker: "BrowserWorker | None" = None


class BrowserWorker:
    def __init__(self, headed: bool = True):
        self.headed = headed
        self.launch_error: Exception | None = None
        self.started = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="greenhouse-browser", daemon=True)
        self._thread.start()

    def call(self, fn, timeout: float = 60):
        if not self.started.wait(timeout):
            raise TimeoutError("The browser did not start.")
        if self.launch_error is not None:
            raise self.launch_error
        box: queue.Queue = queue.Queue(maxsize=1)
        self._queue.put((fn, box))
        status, value = box.get(timeout=timeout)
        if status == "error":
            raise value
        return value

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        if not self.started.is_set() or self.launch_error is not None:
            self._thread.join(timeout=5)
            return
        self._queue.put((None, None))
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=not self.headed)
            context = browser.new_context()
            page = context.new_page()
        except Exception as exc:
            self.launch_error = exc
            self.started.set()
            return
        self.started.set()
        try:
            while True:
                fn, box = self._queue.get()
                if fn is None or box is None:
                    break
                try:
                    box.put(("ok", fn(page)))
                except Exception as exc:
                    box.put(("error", exc))
        finally:
            context.close()
            browser.close()
            playwright.stop()


def start_session(preparation_id: int, *, headed: bool = True) -> AutofillRun:
    with _LOCK:
        _close_active_unlocked()
        run = AutofillRun(
            id=secrets.token_urlsafe(12),
            preparation_id=preparation_id,
            candidate_id=0,
            state="detecting",
            employer="",
            job_title="",
            apply_url="",
        )
        _SESSIONS[run.id] = run
    try:
        with session_scope() as db:
            candidate = candidate_service.get_candidate_or_404(db)
            preparation = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
            run.candidate_id = candidate.id
            run.employer = preparation.snapshot_employer
            run.job_title = preparation.snapshot_job_title
            form_url, note = preparation_service.greenhouse_target(db, preparation)
            run.apply_url = form_url or preparation.snapshot_apply_url
        if not form_url:
            run.state = "failed"
            run.message = note or "This preparation is not a supported Greenhouse application."
            return run
        worker = BrowserWorker(headed=headed)
        run._worker = worker

        def _open(page):
            return open_application(page, run.apply_url)

        html = worker.call(_open, timeout=45)
        plan = _plan_for(run, html)
        run.plan = plan
        run.reviewed = reviewed_fields(plan)
        marker = resume_marker(plan)
        if marker is not None:
            run.reviewed[marker.field_id] = marker
        if run.cancel.is_set():
            run.state = "cancelled"
            run.message = "The browser session was stopped."
            _close_worker(run)
            return run
        if plan.blockers:
            run.state = "needs_review"
            run.message = "A CAPTCHA or verification step is visible. CareerPilot stopped and left the window open."
        else:
            run.state = "ready_to_fill"
            run.message = "Review the plan, then fill the fields you approve. CareerPilot will not submit."
        return run
    except Exception as exc:
        if run.cancel.is_set():
            run.state = "cancelled"
            run.message = "The browser session was stopped."
        else:
            run.state = "failed"
            run.message = _public_error(exc)
        _close_worker(run)
        return run


def fill_session(session_id: str, *, included: set[str], overwrite: set[str], attach_resume: bool) -> AutofillRun:
    run = _get(session_id)
    if run.state not in {"ready_to_fill", "filled_for_review", "needs_review"}:
        raise ValidationError("This browser session cannot be filled right now.")
    if run._worker is None:
        raise ValidationError("The browser window is not open.")
    if run.cancel.is_set():
        run.state = "cancelled"
        run.message = "The fill was cancelled."
        return run
    run.state = "filling"

    def _fill(page):
        if not page.url or page.url.startswith("about:"):
            raise NavigationBlocked("The browser is not on an application page.")
        from app.autofill.urls import classify_apply_url

        if not classify_apply_url(page.url).supported:
            raise NavigationBlocked("The browser left the Greenhouse application page.")
        html = page.content()
        live = _plan_for(run, html)
        if run.cancel.is_set():
            report = FillReport(stopped="cancelled", submitted=False)
            return report, live
        decision = decide_fill(
            run.reviewed,
            live,
            included=included,
            overwrite=overwrite,
            attach_resume=attach_resume,
        )
        if decision.stop_reason:
            report = FillReport(stopped=decision.stop_reason, submitted=False)
            report.outcomes = [
                _outcome(field_id, "blocked", decision.stop_reason) for field_id in included
            ]
            return report, live
        for field_id in decision.stale:
            # recorded after apply
            pass
        path, display = (None, "")
        if decision.resume_field_id:
            path, display = _resume_file(run)
        report = apply_actions(
            page,
            decision.actions,
            resume_field_id=decision.resume_field_id,
            resume_path=path,
            resume_name=display,
            cancel=run.cancel,
        )
        for field_id in decision.preserved:
            report.outcomes.append(_outcome(field_id, "preserved", "The existing value was kept."))
        for field_id in decision.stale:
            report.outcomes.append(_outcome(field_id, "stale", "The form changed since review, so this field was skipped."))
        for field_id in decision.skipped:
            report.outcomes.append(_outcome(field_id, "skipped", "This field is no longer eligible."))
        fresh_html = page.content()
        fresh = _plan_for(run, fresh_html)
        report.unresolved = _unresolved(fresh)
        report.submitted = False
        return report, fresh

    try:
        report, _live = run._worker.call(_fill, timeout=90)
    except Exception as exc:
        if run.cancel.is_set():
            run.state = "cancelled"
            run.message = "The fill was cancelled."
        else:
            run.state = "failed"
            run.message = _public_error(exc)
        return run
    run.result = report
    if report.stopped == "cancelled" or run.cancel.is_set():
        run.state = "cancelled"
        run.message = "The fill was cancelled."
        _close_worker(run)
        return run
    if report.stopped:
        run.state = "needs_review"
        run.message = report.stopped
        return run
    run.state = "filled_for_review"
    run.message = "The browser is open for review. CareerPilot did not submit the application."
    return run


def cancel_session(session_id: str) -> AutofillRun:
    run = _get(session_id)
    run.cancel.set()
    run.state = "cancelled"
    run.message = "The browser session was stopped."
    _close_worker(run)
    return run


def get_session(session_id: str) -> AutofillRun:
    return _get(session_id)


def _get(session_id: str) -> AutofillRun:
    with _LOCK:
        run = _SESSIONS.get(session_id)
    if run is None:
        raise NotFoundError("That autofill session is not open.")
    return run


def _close_active_unlocked() -> None:
    for run in list(_SESSIONS.values()):
        if run.state in {"detecting", "ready_to_fill", "filling", "needs_review", "filled_for_review"}:
            run.cancel.set()
            run.state = "cancelled"
            _close_worker(run)


def _close_worker(run: AutofillRun) -> None:
    worker = run._worker
    run._worker = None
    if worker is not None:
        worker.close()


def _plan_for(run: AutofillRun, html: str) -> AutofillPlan:
    with session_scope() as db:
        candidate = db.get(Candidate, run.candidate_id)
        if candidate is None:
            raise NotFoundError("No candidate profile exists yet. Create one first.")
        return autofill_service.build_plan(db, candidate, run.apply_url, html, run.preparation_id)


def _resume_file(run: AutofillRun) -> tuple[str | None, str]:
    with session_scope() as db:
        candidate = db.get(Candidate, run.candidate_id)
        if candidate is None:
            return None, ""
        preparation = preparation_service.get_preparation_or_404(db, candidate, run.preparation_id)
        plan = run.plan
        if plan is None or not plan.resume.eligible_for_attach:
            return None, ""
        if plan.resume.kind == "tailored":
            path = preparation.pdf_path if plan.resume.file_format == "pdf" else preparation.docx_path
            return path, plan.resume.display_name
        resume = preparation_service_resume(db, preparation.source_resume_id)
        if resume is None:
            return None, ""
        return resume.storage_path, plan.resume.display_name


def preparation_service_resume(db, resume_id):
    if resume_id is None:
        return None
    from app.models.resume import Resume

    return db.get(Resume, resume_id)


def _unresolved(plan: AutofillPlan) -> list[str]:
    labels = [item.label for item in plan.missing_required if item.label]
    labels.extend(item.label for item in plan.answers.missing if item.required and item.label)
    return labels


def _outcome(field_id: str, status: str, detail: str):
    from app.autofill.browser_fill import FieldOutcome

    return FieldOutcome(field_id, field_id, status, detail)


def _public_error(exc: Exception) -> str:
    if isinstance(exc, (NavigationBlocked, NotFoundError, ValidationError)):
        return str(exc)
    return "The browser session could not continue."
