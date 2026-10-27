"""Authorized Greenhouse submission. These tests use local HTML only."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import sync_playwright

from app.autofill.actions import SubmissionBlocked, refuse_submission
from app.autofill.sessions import AutofillRun, _LOCK, _SESSIONS
from app.autofill.submission import (
    SubmissionGate,
    authorization_problem,
    click_authorized_submit,
    find_submit_controls,
    interpret_submission,
    prepare_submission,
)
from app.core.local_auth import load_or_create_token

URL = "https://boards.greenhouse.io/acme/jobs/12345"
OTHER = "https://boards.greenhouse.io/acme/jobs/99999"


def _page(html: str):
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
    page.goto(URL)
    return playwright, browser, page


def _close(playwright, browser) -> None:
    browser.close()
    playwright.stop()


def _form(onsubmit: str, buttons: str) -> str:
    return f"""
    <form id="application" onsubmit="{onsubmit}">
      <label for="email">Email</label>
      <input id="email" name="email" value="ada@example.com">
      {buttons}
    </form>
    <script>window.__clicks = 0;</script>
    """


SEND = '<button type="submit" id="send">Submit application</button>'
SUCCESS = _form("window.__clicks += 1; document.body.innerHTML = '<p>Thank you for applying.</p>'; return false;", SEND)
FAILURE = _form("window.__clicks += 1; document.body.innerHTML = '<p>Please fix the errors below.</p>'; return false;", SEND)
SILENT = _form("window.__clicks += 1; return false;", SEND)


def test_fill_path_still_refuses_submit():
    with pytest.raises(SubmissionBlocked):
        refuse_submission("submit")


def test_authorization_is_specific_and_expires():
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    assert authorization_problem(
        confirm=False,
        preparation_id=9,
        apply_url=URL,
        session_preparation_id=9,
        session_apply_url=URL,
        expires_at=now + timedelta(minutes=2),
        now=now,
    )
    assert "different application" in authorization_problem(
        confirm=True,
        preparation_id=4,
        apply_url=URL,
        session_preparation_id=9,
        session_apply_url=URL,
        expires_at=now + timedelta(minutes=2),
        now=now,
    )
    assert "expired" in authorization_problem(
        confirm=True,
        preparation_id=9,
        apply_url=URL,
        session_preparation_id=9,
        session_apply_url=URL,
        expires_at=now - timedelta(seconds=1),
        now=now,
    )
    assert authorization_problem(
        confirm=True,
        preparation_id=9,
        apply_url=URL,
        session_preparation_id=9,
        session_apply_url=URL,
        expires_at=now + timedelta(minutes=2),
        now=now,
    ) is None


def test_only_one_exact_submit_control_is_usable():
    html = _form("", SEND + '<button type="button" id="auto">Autofill my application</button>')
    controls = find_submit_controls(html)
    assert [item.element_id for item in controls] == ["send"]
    hidden = '<button type="submit" id="old" hidden>Submit application</button>'
    assert find_submit_controls(_form("", hidden + SEND))[0].element_id == "send"
    ambiguous = SEND + '<button type="submit" id="other">Submit application</button>'
    assert len(find_submit_controls(_form("", ambiguous))) == 2
    assert find_submit_controls(_form("", '<button type="submit">Submit application</button>')) == []


def test_prepare_blocks_stale_identity_captcha_and_existing_submission():
    html = _form("", SEND)
    assert prepare_submission(
        html,
        page_url=URL,
        expected_url=URL,
        readiness_status="needs_review",
        failing_details=["Email has not been filled yet."],
        blockers=[],
        already_submitted=False,
    ).ok is False
    captcha = prepare_submission(
        html, page_url=URL, expected_url=URL, readiness_status="ready_to_submit",
        failing_details=[], blockers=["captcha"], already_submitted=False,
    )
    assert captcha.ok is False and "CAPTCHA" in captcha.detail
    wrong = prepare_submission(
        html, page_url=OTHER, expected_url=URL, readiness_status="ready_to_submit",
        failing_details=[], blockers=[], already_submitted=False,
    )
    assert wrong.ok is False and "99999" in wrong.detail
    already = prepare_submission(
        "<p>Thank you for applying.</p>", page_url=URL, expected_url=URL,
        readiness_status="ready_to_submit", failing_details=[], blockers=[], already_submitted=True,
    )
    assert already.ok is False
    many = prepare_submission(
        _form("", SEND + '<button type="submit" id="other">Submit</button>'),
        page_url=URL, expected_url=URL, readiness_status="ready_to_submit",
        failing_details=[], blockers=[], already_submitted=False,
    )
    assert many.ok is False and "More than one" in many.detail


def test_outcome_requires_confirmation_text():
    assert interpret_submission("<p>Thank you for applying.</p>", clicked=True, timed_out=False)[0] == "submitted"
    assert interpret_submission("<script>thank you for applying</script><p>Loading</p>", clicked=True, timed_out=False)[0] == "confirmation_unknown"
    assert interpret_submission("<p>Please fix the errors below.</p>", clicked=True, timed_out=False)[0] == "submission_failed"
    assert interpret_submission("<p>You are signed in.</p>", clicked=True, timed_out=True)[0] == "confirmation_unknown"
    assert interpret_submission("<p>Still here.</p>", clicked=False, timed_out=False)[0] == "submission_failed"


def _open_run(**overrides) -> AutofillRun:
    run = AutofillRun(
        id="sess-submit",
        preparation_id=9,
        candidate_id=1,
        state="filled_for_review",
        employer="Northwind",
        job_title="Backend Intern",
        apply_url=URL,
        submit_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    for key, value in overrides.items():
        setattr(run, key, value)
    with _LOCK:
        _SESSIONS[run.id] = run
    return run


def _close_run(run: AutofillRun) -> None:
    with _LOCK:
        _SESSIONS.pop(run.id, None)


def test_submit_route_rejects_missing_confirmation_and_a_stale_session(client):
    run = _open_run()
    body = {"confirm": True, "preparation_id": 9, "apply_url": URL}
    headers = {"X-CareerPilot-Token": load_or_create_token()}
    try:
        denied = client.post(f"/api/autofill/sessions/{run.id}/submit", json=body)
        assert denied.status_code == 401
        unconfirmed = client.post(
            f"/api/autofill/sessions/{run.id}/submit",
            json={**body, "confirm": False},
            headers=headers,
        )
        assert unconfirmed.status_code == 409
        assert "not confirmed" in unconfirmed.text
        other = client.post(
            f"/api/autofill/sessions/{run.id}/submit",
            json={**body, "preparation_id": 4},
            headers=headers,
        )
        assert other.status_code == 409
        assert "different application" in other.text
        run.submit_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        expired = client.post(f"/api/autofill/sessions/{run.id}/submit", json=body, headers=headers)
        assert expired.status_code == 409
        assert "expired" in expired.text
        run.submit_expires_at = None
        unauthorized = client.post(f"/api/autofill/sessions/{run.id}/submit", json=body, headers=headers)
        assert unauthorized.status_code == 409
        assert "not authorized" in unauthorized.text
    finally:
        _close_run(run)


def test_only_one_gate_holder_can_submit():
    gate = SubmissionGate()
    results = []

    def grab():
        results.append(gate.acquire())

    threads = [threading.Thread(target=grab) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1


def test_authorized_local_form_submits_once_and_confirms():
    playwright, browser, page = _page(SUCCESS)
    try:
        prepared = prepare_submission(
            page.content(), page_url=page.url, expected_url=URL, readiness_status="ready_to_submit",
            failing_details=[], blockers=[], already_submitted=False,
        )
        assert prepared.ok and prepared.control is not None
        with pytest.raises(SubmissionBlocked):
            click_authorized_submit(page, prepared.control, authorized=False)
        assert page.evaluate("window.__clicks") == 0
        clicked = click_authorized_submit(page, prepared.control, authorized=True, timeout_ms=2000)
        status, _note = interpret_submission(clicked.html, clicked=clicked.clicked, timed_out=clicked.timed_out)
        assert status == "submitted"
        assert page.evaluate("window.__clicks") == 1
        again = prepare_submission(
            page.content(), page_url=page.url, expected_url=URL, readiness_status="ready_to_submit",
            failing_details=[], blockers=[], already_submitted=True,
        )
        assert again.ok is False
    finally:
        _close(playwright, browser)


def test_local_form_failure_timeout_and_ambiguous_controls_do_not_retry():
    playwright, browser, page = _page(FAILURE)
    try:
        prepared = prepare_submission(
            page.content(), page_url=page.url, expected_url=URL, readiness_status="ready_to_submit",
            failing_details=[], blockers=[], already_submitted=False,
        )
        clicked = click_authorized_submit(page, prepared.control, authorized=True, timeout_ms=2000)
        assert interpret_submission(clicked.html, clicked=True, timed_out=clicked.timed_out)[0] == "submission_failed"
        assert page.evaluate("window.__clicks") == 1
    finally:
        _close(playwright, browser)

    playwright, browser, page = _page(SILENT)
    try:
        prepared = prepare_submission(
            page.content(), page_url=page.url, expected_url=URL, readiness_status="ready_to_submit",
            failing_details=[], blockers=[], already_submitted=False,
        )
        clicked = click_authorized_submit(page, prepared.control, authorized=True, timeout_ms=400)
        status, note = interpret_submission(clicked.html, clicked=clicked.clicked, timed_out=clicked.timed_out)
        assert status == "confirmation_unknown"
        assert "will not retry" in note
        assert page.evaluate("window.__clicks") == 1
    finally:
        _close(playwright, browser)

    ambiguous = prepare_submission(
        _form("", SEND + '<button type="submit" id="other">Submit application</button>'),
        page_url=URL, expected_url=URL, readiness_status="ready_to_submit",
        failing_details=[], blockers=[], already_submitted=False,
    )
    assert ambiguous.ok is False
