"""One visible Greenhouse browser at a time. The window stays open for review.

Playwright calls stay on the thread that launched Chromium. Filling never
clicks Submit. Submission is a separate confirmation for this session only.
"""

from __future__ import annotations

import queue
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

from app.autofill.actions import decide_fill, resume_marker, reviewed_fields
from app.autofill.browser_fill import FillReport, NavigationBlocked, apply_actions, open_application
from app.autofill.mapping import AutofillPlan
from app.autofill.submission import SubmissionGate
from app.autofill.urls import classify_apply_url, same_greenhouse_application
from app.core.db import session_scope
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger, log_extra
from app.models.candidate import Candidate
from app.services import autofill_service, candidate_service, preparation_service

logger = get_logger(__name__)
_EMAIL = re.compile(r"\S+@\S+")
_LONG_NUMBER = re.compile(r"\d{6,}")

_LOCK = threading.Lock()
_SESSIONS: dict[str, "AutofillRun"] = {}
_KEEP_OPEN = {"detecting", "ready_to_fill", "filling", "needs_review", "filled_for_review"}


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
    employment_type: str = "unknown"
    eligibility_reasons: list = field(default_factory=list)
    work_authorization_status: str = "unknown"
    sponsorship: str = "unknown"
    identity_matches: bool = False
    identity_detail: str = "The open page has not been compared with the selected preparation."
    form_found: bool = False
    already_submitted: bool | None = None
    fill_attempted: bool = False
    included_field_ids: set[str] = field(default_factory=set)
    application_status: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submit_expires_at: datetime | None = None
    submit_gate: SubmissionGate = field(default_factory=SubmissionGate)
    cancel: threading.Event = field(default_factory=threading.Event)
    reviewed: dict = field(default_factory=dict)
    opened: threading.Event = field(default_factory=threading.Event)
    _worker: "BrowserWorker | None" = None


class BrowserWorker:
    def __init__(self, headed: bool = True, session_id: str = ""):
        self.headed = headed
        self.session_id = session_id
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
        _log("browser_launch_started", session_id=self.session_id)
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
        _log("browser_launch_succeeded", session_id=self.session_id)
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
        existing = _reusable_unlocked(preparation_id)
        if existing is not None:
            run = existing
            owner = False
        else:
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
            owner = True
            _log("session_created", session_id=run.id, preparation_id=preparation_id)
    if not owner:
        if not run.opened.wait(60):
            raise ValidationError("This application is still opening. CareerPilot did not start a second browser.")
        return run
    try:
        with session_scope() as db:
            candidate = candidate_service.get_candidate_or_404(db)
            preparation = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
            run.candidate_id = candidate.id
            run.employer = preparation.snapshot_employer
            run.job_title = preparation.snapshot_job_title
            _remember_eligibility(run, db, candidate, preparation)
            form_url, note = preparation_service.greenhouse_target(db, preparation)
            run.apply_url = form_url or preparation.snapshot_apply_url
        if not form_url:
            run.state = "failed"
            run.message = note or "This preparation is not a supported Greenhouse application."
            _log("session_failed", session_id=run.id, preparation_id=preparation_id, error_type="ValidationError", reason=run.message)
            return run
        worker = BrowserWorker(headed=headed, session_id=run.id)
        run._worker = worker

        def _open(page):
            _log("navigation_started", session_id=run.id, preparation_id=run.preparation_id)
            html = open_application(page, run.apply_url)
            _log("navigation_succeeded", session_id=run.id, preparation_id=run.preparation_id)
            return html, page.url

        html, final_url = worker.call(_open, timeout=45)
        _log("page_validation_started", session_id=run.id, preparation_id=run.preparation_id)
        matches, detail = same_greenhouse_application(final_url, run.apply_url)
        _log("page_validation_succeeded", session_id=run.id, preparation_id=run.preparation_id, identity_matches=matches)
        run.identity_matches = matches
        run.identity_detail = detail
        plan = _plan_for(run, html, final_url)
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
        if not matches:
            run.state = "needs_review"
            run.message = detail
        elif plan.blockers:
            run.state = "needs_review"
            run.message = "A CAPTCHA or verification step is visible. CareerPilot stopped and left the window open."
        else:
            run.state = "ready_to_fill"
            run.message = "Review the plan, then fill the fields you approve. CareerPilot will not submit."
        _persist_readiness(run)
        _log("session_ready", session_id=run.id, preparation_id=run.preparation_id, state=run.state)
        return run
    except Exception as exc:
        if run.cancel.is_set():
            run.state = "cancelled"
            run.message = "The browser session was stopped."
        else:
            run.state = "failed"
            run.message = _public_error(exc)
            _log(
                "session_failed",
                session_id=run.id,
                preparation_id=run.preparation_id,
                error_type=type(exc).__name__,
                reason=_safe_reason(exc),
            )
        _close_worker(run)
        return run
    finally:
        run.opened.set()


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
    run.fill_attempted = True
    run.included_field_ids = set(included)

    def _fill(page):
        if not page.url or page.url.startswith("about:"):
            raise NavigationBlocked("The browser is not on an application page.")
        if not classify_apply_url(page.url).supported:
            raise NavigationBlocked("The browser left the Greenhouse application page.")
        matches, detail = same_greenhouse_application(page.url, run.apply_url)
        run.identity_matches = matches
        run.identity_detail = detail
        html = page.content()
        live = _plan_for(run, html, page.url)
        if not matches:
            report = FillReport(stopped=detail, submitted=False)
            return report, live
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
        still_same, still_detail = same_greenhouse_application(page.url, run.apply_url)
        run.identity_matches = still_same
        run.identity_detail = still_detail
        fresh_html = page.content()
        fresh = _plan_for(run, fresh_html, page.url)
        report.unresolved = _unresolved(fresh)
        report.submitted = False
        if not still_same:
            report.stopped = still_detail
        return report, fresh

    try:
        report, live = run._worker.call(_fill, timeout=90)
    except Exception as exc:
        if run.cancel.is_set():
            run.state = "cancelled"
            run.message = "The fill was cancelled."
        else:
            run.state = "failed"
            run.message = _public_error(exc)
        return run
    run.result = report
    if live is not None and run.plan is not None:
        run.plan.blockers = list(live.blockers)
    if report.stopped == "cancelled" or run.cancel.is_set():
        run.state = "cancelled"
        run.message = "The fill was cancelled."
        _close_worker(run)
        return run
    if report.stopped:
        run.state = "needs_review"
        run.message = report.stopped
        _persist_readiness(run)
        return run
    run.state = "filled_for_review"
    run.message = "The browser is open for review. CareerPilot did not submit the application."
    _persist_readiness(run)
    return run


def submit_session(session_id: str, *, confirm: bool, preparation_id: int, apply_url: str) -> AutofillRun:
    """Submit only when this request confirms the open preparation and the live page is ready."""
    from datetime import datetime, timezone

    from app.autofill.readiness import readiness_for_run
    from app.autofill.submission import (
        authorization_problem,
        click_authorized_submit,
        interpret_submission,
        prepare_submission,
    )
    from app.models.enums import ApplicationStatus
    from app.services.application_tracking import claim_for_submission, record_submission_outcome

    run = _get(session_id)
    now = datetime.now(timezone.utc)
    problem = authorization_problem(
        confirm=confirm,
        preparation_id=preparation_id,
        apply_url=apply_url,
        session_preparation_id=run.preparation_id,
        session_apply_url=run.apply_url,
        expires_at=run.submit_expires_at,
        now=now,
    )
    if problem:
        raise ValidationError(problem)
    if run._worker is None:
        raise ValidationError("The browser window is not open.")
    if run.state not in {"ready_to_fill", "filled_for_review", "needs_review"}:
        raise ValidationError("This browser session cannot submit right now.")
    if not run.submit_gate.acquire():
        raise ValidationError("Another submission is already in progress.")
    claimed_id: int | None = None
    try:
        def _submit(page):
            nonlocal claimed_id
            if not page.url or not classify_apply_url(page.url).supported:
                return "needs_review", "The browser left the Greenhouse application page.", False
            html = page.content()
            live = _plan_for(run, html, page.url)
            run.plan = live
            if run.plan is not None:
                run.plan.blockers = list(live.blockers)
            readiness = readiness_for_run(run)
            prepared = prepare_submission(
                html,
                page_url=page.url,
                expected_url=run.apply_url,
                readiness_status=readiness.status,
                failing_details=[item.detail for item in readiness.checks if item.status != "passed"],
                blockers=list(live.blockers),
                already_submitted=run.already_submitted,
            )
            if not prepared.ok or prepared.control is None:
                return "needs_review", prepared.detail, False
            with session_scope() as db:
                claimed = claim_for_submission(
                    db,
                    candidate_id=run.candidate_id,
                    preparation_id=run.preparation_id,
                    session_started_at=run.started_at,
                )
                claimed_id = claimed.id
            clicked = click_authorized_submit(page, prepared.control, authorized=True)
            if not clicked.clicked:
                status, note = "submission_failed", clicked.error or "The submit control was not used. Nothing was sent."
            else:
                status, note = interpret_submission(clicked.html, clicked=True, timed_out=clicked.timed_out)
            with session_scope() as db:
                saved = record_submission_outcome(
                    db,
                    application_id=claimed_id,
                    status=ApplicationStatus(status),
                    note=note,
                )
            fresh = page.content()
            _plan_for(run, fresh, page.url)
            report = run.result or FillReport()
            report.submitted = status == "submitted"
            report.stopped = None if status == "submitted" else note
            run.result = report
            return status, note, True

        try:
            status, note, sent = run._worker.call(_submit, timeout=90)
        except ValidationError:
            raise
        except (TimeoutError, queue.Empty):
            if claimed_id is None:
                _hold_review(run, "The browser did not answer in time, so nothing was submitted.")
            else:
                _record_unknown(run, claimed_id)
            return run
        except Exception:
            if claimed_id is None:
                _hold_review(run, "The submission could not start, so nothing was sent.")
            else:
                _record_unknown(run, claimed_id)
            return run
        if not sent:
            _hold_review(run, note)
            return run
        run.application_status = status
        run.state = status
        run.message = note
        if status != "submitted":
            run.submit_expires_at = None
        return run
    finally:
        run.submit_gate.release()


def _hold_review(run: AutofillRun, detail: str) -> None:
    from app.services.application_tracking import return_to_review

    with session_scope() as db:
        row = return_to_review(db, candidate_id=run.candidate_id, preparation_id=run.preparation_id, detail=detail)
    run.state = "needs_review"
    run.message = detail
    run.application_status = row.status.value if row is not None else "needs_review"


def _record_unknown(run: AutofillRun, application_id: int) -> None:
    from app.models.enums import ApplicationStatus
    from app.services.application_tracking import record_submission_outcome

    note = "The browser did not answer in time. Check the employer page and record what you saw. CareerPilot will not retry."
    with session_scope() as db:
        try:
            record_submission_outcome(
                db,
                application_id=application_id,
                status=ApplicationStatus.CONFIRMATION_UNKNOWN,
                note=note,
            )
        except ValidationError:
            return
    run.state = "confirmation_unknown"
    run.message = note
    run.application_status = "confirmation_unknown"
    run.submit_expires_at = None


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


def _reusable_unlocked(preparation_id: int) -> AutofillRun | None:
    for run in _SESSIONS.values():
        if run.preparation_id == preparation_id and run.state in _KEEP_OPEN and not run.cancel.is_set():
            return run
    return None


def _close_active_unlocked() -> None:
    for run in list(_SESSIONS.values()):
        if run.state in _KEEP_OPEN:
            run.cancel.set()
            run.state = "cancelled"
            run.opened.set()
            _close_worker(run)


def _close_worker(run: AutofillRun) -> None:
    worker = run._worker
    run._worker = None
    if worker is not None:
        _log("browser_cleanup", session_id=run.id, preparation_id=run.preparation_id)
        worker.close()


def _plan_for(run: AutofillRun, html: str, url: str | None = None) -> AutofillPlan:
    with session_scope() as db:
        candidate = db.get(Candidate, run.candidate_id)
        if candidate is None:
            raise NotFoundError("No candidate profile exists yet. Create one first.")
        plan = autofill_service.build_plan(db, candidate, url or run.apply_url, html, run.preparation_id)
    run.form_found = plan.form_found
    from app.autofill.readiness import submission_state

    run.already_submitted = submission_state(html, plan.form_found)
    return plan


def _persist_readiness(run: AutofillRun) -> None:
    if not run.candidate_id or not run.preparation_id:
        return
    from app.autofill.readiness import readiness_for_run
    from app.models.enums import ApplicationStatus
    from app.services.application_tracking import apply_readiness

    with session_scope() as db:
        row = apply_readiness(
            db,
            candidate_id=run.candidate_id,
            preparation_id=run.preparation_id,
            readiness=readiness_for_run(run),
        )
        # Copy the status before session_scope closes the session. Reading it
        # afterwards raises DetachedInstanceError and the opener treats that
        # as a browser failure.
        status = row.status
    run.application_status = status.value
    if status is ApplicationStatus.READY_TO_SUBMIT:
        run.submit_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    else:
        run.submit_expires_at = None


def _remember_eligibility(run: AutofillRun, db, candidate: Candidate, preparation) -> None:
    from app.models.job import Job
    from app.services.eligibility_service import assess_eligibility

    run.work_authorization_status = candidate.work_authorization_status.value
    run.sponsorship = candidate.requires_sponsorship.value
    job = db.get(Job, preparation.job_id) if preparation.job_id else None
    if job is None:
        run.employment_type = "unknown"
        run.eligibility_reasons = []
        return
    _overall, reasons = assess_eligibility(candidate, job)
    run.employment_type = job.employment_type.value
    run.eligibility_reasons = reasons


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
            return path, plan.resume.upload_name or plan.resume.display_name
        resume = preparation_service_resume(db, preparation.source_resume_id)
        if resume is None:
            return None, ""
        return resume.storage_path, plan.resume.upload_name or plan.resume.display_name


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


def _log(event: str, **fields) -> None:
    logger.info(event, extra=log_extra(**fields))


def _safe_reason(exc: Exception) -> str:
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    text = _EMAIL.sub("[redacted]", text)
    text = _LONG_NUMBER.sub("[redacted]", text)
    return text[:200]


def _public_error(exc: Exception) -> str:
    if isinstance(exc, (NavigationBlocked, NotFoundError, ValidationError)):
        return str(exc)
    return "The browser session could not continue."
