"""The Greenhouse window stays open for review and is not replaced by a duplicate open."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.autofill.browser_fill import FillReport, NavigationBlocked
from app.autofill.mapping import AutofillPlan
from app.autofill.sessions import AutofillRun, cancel_session, fill_session, start_session
from app.core.exceptions import ValidationError

URL = "https://boards.greenhouse.io/acme/jobs/12345"
OTHER = "https://boards.greenhouse.io/acme/jobs/99999"


class FakeWorker:
    created = 0

    def __init__(self, headed: bool = True):
        FakeWorker.created += 1
        self.headed = headed
        self.closed = False
        self.result = ("<form id='application'></form>", URL)
        self.error: Exception | None = None
        self.started = threading.Event()
        self.release = threading.Event()
        self.hold = False

    def call(self, fn, timeout: float = 60):
        self.started.set()
        if self.hold:
            assert self.release.wait(2)
        if self.error is not None:
            raise self.error
        return self.result

    def close(self) -> None:
        self.closed = True
        self.release.set()


@pytest.fixture
def sessions(monkeypatch):
    from app.autofill import sessions as mod

    saved = dict(mod._SESSIONS)
    mod._SESSIONS.clear()
    FakeWorker.created = 0
    holder = {"worker": None, "plan": AutofillPlan(url=URL, supported=True, rejection_reason=None, form_found=True)}

    @contextmanager
    def scope():
        yield object()

    def worker_factory(headed: bool = True):
        worker = FakeWorker(headed=headed)
        holder["worker"] = worker
        return worker

    monkeypatch.setattr(mod, "session_scope", scope)
    monkeypatch.setattr(mod, "BrowserWorker", worker_factory)
    monkeypatch.setattr(mod.candidate_service, "get_candidate_or_404", lambda db: SimpleNamespace(id=1))
    monkeypatch.setattr(
        mod.preparation_service,
        "get_preparation_or_404",
        lambda db, candidate, preparation_id: SimpleNamespace(
            id=preparation_id,
            job_id=4,
            snapshot_employer="Northwind",
            snapshot_job_title="Backend Intern",
            snapshot_apply_url=URL,
        ),
    )
    monkeypatch.setattr(mod.preparation_service, "greenhouse_target", lambda db, preparation: (URL, ""))
    monkeypatch.setattr(mod, "_remember_eligibility", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_persist_readiness", lambda run: setattr(run, "application_status", "needs_review"))

    def plan_for(run, html, url=None):
        plan = holder["plan"]
        run.form_found = plan.form_found
        run.already_submitted = False
        return plan

    monkeypatch.setattr(mod, "_plan_for", plan_for)
    yield holder, mod
    mod._SESSIONS.clear()
    mod._SESSIONS.update(saved)


def test_duplicate_open_reuses_the_same_browser(sessions):
    holder, _mod = sessions
    first = threading.Event()

    class Holding(FakeWorker):
        def call(self, fn, timeout: float = 60):
            first.set()
            assert self.release.wait(2)
            return self.result

    from app.autofill import sessions as mod

    def factory(headed: bool = True):
        worker = Holding(headed=headed)
        holder["worker"] = worker
        return worker

    mod.BrowserWorker = factory
    results = []

    def open_one():
        results.append(start_session(9, headed=True))

    first_thread = threading.Thread(target=open_one)
    second_thread = threading.Thread(target=open_one)
    first_thread.start()
    assert first.wait(2)
    second_thread.start()
    holder["worker"].release.set()
    first_thread.join(3)
    second_thread.join(3)
    assert len(results) == 2
    assert results[0].id == results[1].id
    assert FakeWorker.created == 1
    assert holder["worker"].closed is False
    assert results[0].state == "ready_to_fill"
    assert results[0].state != "submitted"


def test_unknown_eligibility_and_unanswered_questions_leave_the_window_open(sessions):
    holder, _mod = sessions
    holder["plan"].missing_required = []
    holder["plan"].sensitive = []
    run = start_session(9, headed=True)
    assert run.state == "ready_to_fill"
    assert run.application_status == "needs_review"
    assert holder["worker"].closed is False
    assert run.result is None or run.result.submitted is False


def test_captcha_and_identity_mismatch_stay_open_for_review(sessions):
    holder, _mod = sessions
    holder["plan"].blockers = ["captcha"]
    blocked = start_session(9, headed=True)
    assert blocked.state == "needs_review"
    assert "window open" in blocked.message
    assert holder["worker"].closed is False

    from app.autofill import sessions as mod

    mod._SESSIONS.clear()
    FakeWorker.created = 0
    holder["plan"].blockers = []
    holder["worker"] = None

    def mismatch_worker(headed: bool = True):
        worker = FakeWorker(headed=headed)
        worker.result = ("<form></form>", OTHER)
        holder["worker"] = worker
        return worker

    mod.BrowserWorker = mismatch_worker
    mismatched = start_session(9, headed=True)
    assert mismatched.state == "needs_review"
    assert holder["worker"].closed is False
    assert mismatched.state != "submitted"


def test_navigation_failure_closes_the_browser_with_a_public_message(sessions):
    holder, mod = sessions

    def broken(headed: bool = True):
        worker = FakeWorker(headed=headed)
        worker.error = NavigationBlocked("The browser left the Greenhouse application page.")
        holder["worker"] = worker
        return worker

    mod.BrowserWorker = broken
    run = start_session(9, headed=True)
    assert run.state == "failed"
    assert run.message == "The browser left the Greenhouse application page."
    assert "Traceback" not in run.message
    assert holder["worker"].closed is True


def test_fill_that_needs_review_does_not_close_or_submit(sessions):
    holder, mod = sessions
    opened = start_session(9, headed=True)
    worker = holder["worker"]

    def fill_call(fn, timeout: float = 60):
        return FillReport(stopped="A required answer is missing.", submitted=False), holder["plan"]

    worker.call = fill_call
    filled = fill_session(opened.id, included={"phone"}, overwrite=set(), attach_resume=False)
    assert filled.state == "needs_review"
    assert filled.result.submitted is False
    assert worker.closed is False


def test_stop_still_closes_the_session(sessions):
    holder, _mod = sessions
    opened = start_session(9, headed=True)
    stopped = cancel_session(opened.id)
    assert stopped.state == "cancelled"
    assert holder["worker"].closed is True
    with pytest.raises(ValidationError, match="cannot be filled"):
        fill_session(opened.id, included=set(), overwrite=set(), attach_resume=False)


def test_a_different_job_replaces_the_open_browser(sessions):
    holder, _mod = sessions
    first = start_session(9, headed=True)
    first_worker = holder["worker"]
    second = start_session(10, headed=True)
    assert second.id != first.id
    assert first_worker.closed is True
    assert holder["worker"].closed is False
    assert first.state == "cancelled"
