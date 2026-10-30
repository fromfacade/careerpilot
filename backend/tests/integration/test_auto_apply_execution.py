"""Auto-Apply uses the existing Greenhouse submit path. These tests use fictional data and local HTML."""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auto_apply.execution import evaluate_and_reserve
from app.autofill.sessions import AutofillRun, _LOCK, _SESSIONS, _arm_auto_apply, submit_session
from app.models.application import ApplicationEvent, TrackedApplication
from app.models.auto_apply import AutoApplyReservation
from app.models.enums import (
    ApplicationStatus,
    Eligibility,
    EmploymentType,
    JobProvider,
    Relevance,
    ResumeFileFormat,
    RoleCategory,
)
from app.models.job import Job, JobAssessment, JobLocation
from app.models.job_source import Employer, JobSource
from app.models.preparation import ApplicationPreparation
from app.models.resume import Resume
from tests.unit.test_application_submission import FAILURE, SILENT, SUCCESS, URL, _close, _page

NOW = datetime(2026, 10, 28, 20, tzinfo=timezone.utc)


class _Ready:
    status = "ready_to_submit"
    checks: list = []


def _failed(code: str):
    check = type("Check", (), {"code": code, "status": "needs_review", "detail": code})()
    return type("Readiness", (), {"status": "needs_review", "checks": [check]})()


def _candidate(client, email="ada.auto-exec@example.com"):
    created = client.post("/api/candidate", json={"full_name": "Ada Lovelace", "email": email})
    assert created.status_code == 201, created.text
    return created.json()


def _enable(client, resume_id, **overrides):
    body = {
        "enabled": True,
        "acknowledge": True,
        "provider": "greenhouse",
        "job_categories": ["swe_backend"],
        "employment_types": ["internship"],
        "locations": ["Santa Cruz, CA"],
        "min_match_score": 70,
        "max_per_day": 2,
        "max_per_session": 2,
        "resume_ids": [resume_id],
        "expires_at": "2027-06-01T00:00:00Z",
    }
    body.update(overrides)
    saved = client.put("/api/candidate/auto-apply", json=body)
    assert saved.status_code == 200, saved.text
    return saved.json()


def _resume(db, candidate_id, *, approved=True):
    row = Resume(
        candidate_id=candidate_id,
        original_filename="fictional.pdf",
        file_format=ResumeFileFormat.PDF,
        storage_path=f"resumes/fictional-{candidate_id}-{approved}-{uuid.uuid4().hex}.pdf",
        file_size_bytes=128,
        sha256_checksum=uuid.uuid4().hex,
        profile_name="Fictional backend profile",
        is_approved=approved,
    )
    db.add(row)
    db.flush()
    return row


def _application(db, candidate_id, resume_id, *, external_id="fictional-intern", status=ApplicationStatus.READY_TO_SUBMIT, score=80, category=RoleCategory.SWE_BACKEND, location="Santa Cruz, CA", eligibility=Eligibility.ELIGIBLE):
    employer = Employer(name=f"Fictional Labs {external_id}")
    db.add(employer)
    db.flush()
    source = JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token=external_id)
    db.add(source)
    db.flush()
    job = Job(
        job_source_id=source.id,
        external_id=external_id,
        title="Backend Intern",
        employment_type=EmploymentType.INTERNSHIP,
        role_category=category,
        description_text="Build fictional services.",
        apply_url=URL,
        canonical_url=f"https://example.test/jobs/{external_id}",
        content_hash=f"hash-{external_id}",
        dedupe_key=f"fiction|{external_id}",
        raw_payload={"id": external_id},
    )
    db.add(job)
    db.flush()
    db.add(JobLocation(job_id=job.id, raw_text=location, is_remote=False))
    db.add(
        JobAssessment(
            job_id=job.id,
            candidate_id=candidate_id,
            eligibility=eligibility,
            eligibility_reasons=[],
            relevance=Relevance.RELEVANT,
            relevance_reasons=[],
            match_score=score,
            match_reasons=[],
        )
    )
    preparation = ApplicationPreparation(
        candidate_id=candidate_id,
        job_id=job.id,
        source_resume_id=resume_id,
        snapshot_job_title="Backend Intern",
        snapshot_employer=employer.name,
        snapshot_description="Build fictional services.",
        snapshot_apply_url=URL,
        analysis={},
        match_report={},
        tailored_resume={},
    )
    db.add(preparation)
    db.flush()
    tracked = TrackedApplication(
        candidate_id=candidate_id,
        job_id=job.id,
        employer=employer.name,
        preparation_id=preparation.id,
        resume_id=resume_id,
        status=status,
    )
    db.add(tracked)
    db.flush()
    return preparation, tracked


def _scope(db_session):
    @contextmanager
    def scope():
        yield db_session
        db_session.commit()

    return scope


def _run(preparation, candidate_id, page):
    run = AutofillRun(
        id=f"auto-{uuid.uuid4().hex}",
        preparation_id=preparation.id,
        candidate_id=candidate_id,
        state="filled_for_review",
        employer="Fictional Labs",
        job_title="Backend Intern",
        apply_url=URL,
        auto_apply_armed=True,
        mode="auto_apply",
        phase="checking_readiness",
        already_submitted=False,
        started_at=datetime.now(timezone.utc),
    )

    class _Worker:
        def call(self, fn, timeout=90):
            return fn(page)

    run._worker = _Worker()
    with _LOCK:
        _SESSIONS[run.id] = run
    return run


def test_auto_apply_is_review_mode_until_the_grant_is_active(client, db_session):
    candidate = _candidate(client)
    run = AutofillRun(
        id="arm",
        preparation_id=1,
        candidate_id=candidate["id"],
        state="ready_to_fill",
        employer="",
        job_title="",
        apply_url=URL,
    )
    _arm_auto_apply(run, db_session, True)
    assert run.auto_apply_armed is False
    assert run.mode == "review"


def test_grant_checks_block_submission_without_a_reservation(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: NOW)
    candidate = _candidate(client, "ada.blocked@example.com")
    resume = _resume(db_session, candidate["id"])
    preparation, _tracked = _application(db_session, candidate["id"], resume.id)
    _enable(client, resume.id)
    blocked = evaluate_and_reserve(
        db_session,
        candidate_id=candidate["id"],
        preparation_id=preparation.id,
        readiness=_failed("approved_answers"),
        now=NOW,
    )
    assert blocked.permitted is False
    assert "unapproved" in blocked.reasons[0]
    assert blocked.reservation_id is None
    assert db_session.scalar(select(AutoApplyReservation.id)) is None


def test_scope_resume_eligibility_and_limits_refuse_the_grant(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: NOW)
    candidate = _candidate(client, "ada.scope@example.com")
    resume = _resume(db_session, candidate["id"])
    other = _resume(db_session, candidate["id"], approved=False)
    preparation, tracked = _application(db_session, candidate["id"], resume.id)
    _enable(client, resume.id, max_per_day=1, max_per_session=5)

    def decide_for(**job_changes):
        external_id = job_changes.pop("external_id", uuid.uuid4().hex)
        preparation_id = _application(
            db_session, candidate["id"], resume.id, external_id=external_id, **job_changes
        )[0].id
        return evaluate_and_reserve(
            db_session,
            candidate_id=candidate["id"],
            preparation_id=preparation_id,
            readiness=_Ready(),
            now=NOW,
        )

    category = decide_for(category=RoleCategory.SWE_FRONTEND, external_id="front")
    location = decide_for(location="Seattle, WA", external_id="seattle")
    score = decide_for(score=69, external_id="low-score")
    unknown = decide_for(eligibility=Eligibility.UNKNOWN, external_id="unknown-fit")
    unapproved = evaluate_and_reserve(
        db_session,
        candidate_id=candidate["id"],
        preparation_id=_application(db_session, candidate["id"], other.id, external_id="bad-resume")[0].id,
        readiness=_Ready(),
        now=NOW,
    )
    expired = client.put(
        "/api/candidate/auto-apply",
        json={
            "enabled": True,
            "acknowledge": True,
            "provider": "greenhouse",
            "job_categories": ["swe_backend"],
            "employment_types": ["internship"],
            "locations": ["Santa Cruz, CA"],
            "min_match_score": 70,
            "max_per_day": 1,
            "max_per_session": 5,
            "resume_ids": [resume.id],
            "expires_at": "2020-01-01T00:00:00Z",
        },
    )
    assert expired.status_code == 422
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: datetime(2027, 7, 1, tzinfo=timezone.utc))
    client.put(
        "/api/candidate/auto-apply",
        json={
            "enabled": True,
            "acknowledge": True,
            "provider": "greenhouse",
            "job_categories": ["swe_backend"],
            "employment_types": ["internship"],
            "locations": ["Santa Cruz, CA"],
            "min_match_score": 70,
            "max_per_day": 1,
            "max_per_session": 5,
            "resume_ids": [resume.id],
            "expires_at": "2027-06-01T00:00:00Z",
        },
    )
    stale = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=preparation.id, readiness=_Ready(), now=datetime(2027, 7, 1, tzinfo=timezone.utc)
    )
    revoked = client.put(
        "/api/candidate/auto-apply",
        json={
            "enabled": False,
            "acknowledge": False,
            "provider": "greenhouse",
            "job_categories": ["swe_backend"],
            "employment_types": ["internship"],
            "locations": ["Santa Cruz, CA"],
            "min_match_score": 70,
            "max_per_day": 1,
            "max_per_session": 5,
            "resume_ids": [resume.id],
            "expires_at": "2027-06-01T00:00:00Z",
        },
    )
    assert revoked.status_code == 200
    off = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=preparation.id, readiness=_Ready(), now=NOW
    )
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: NOW)
    tracked.status = ApplicationStatus.SUBMITTED
    db_session.flush()
    _enable(client, resume.id)
    duplicate = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=preparation.id, readiness=_Ready(), now=NOW
    )
    assert "authorized categories" in category.reasons[0]
    assert "authorized locations" in location.reasons[0]
    assert "match score" in score.reasons[0]
    assert "unknown" in unknown.reasons[0].casefold()
    assert unapproved.permitted is False
    assert "approved profile" in unapproved.reasons[0]
    assert stale.permitted is False
    assert "expired" in stale.reasons[0]
    assert off.permitted is False
    assert duplicate.permitted is False
    assert "already been submitted" in duplicate.reasons[0]
    for result in (category, location, score, unknown, unapproved, stale, off, duplicate):
        assert result.reservation_id is None


def test_one_held_slot_blocks_the_next_application(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: NOW)
    candidate = _candidate(client, "ada.limit@example.com")
    resume = _resume(db_session, candidate["id"])
    first, _tracked = _application(db_session, candidate["id"], resume.id, external_id="limit-one")
    second, _other = _application(db_session, candidate["id"], resume.id, external_id="limit-two")
    _enable(client, resume.id, max_per_day=1, max_per_session=5)
    allowed = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=first.id, readiness=_Ready(), now=NOW
    )
    daily = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=second.id, readiness=_Ready(), now=NOW
    )
    assert allowed.permitted is True
    assert allowed.reservation_id is not None
    assert daily.permitted is False
    assert "daily application limit" in daily.reasons[0]
    _enable(client, resume.id, max_per_day=5, max_per_session=1)
    session_block = evaluate_and_reserve(
        db_session, candidate_id=candidate["id"], preparation_id=second.id, readiness=_Ready(), now=NOW
    )
    assert session_block.permitted is False
    assert "session application limit" in session_block.reasons[0]


def test_sensitive_captcha_and_required_fields_do_not_reserve(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: NOW)
    candidate = _candidate(client, "ada.safety@example.com")
    resume = _resume(db_session, candidate["id"])
    preparation, _tracked = _application(db_session, candidate["id"], resume.id, external_id="safety")
    _enable(client, resume.id)
    for code, phrase in (
        ("required_fields", "incomplete"),
        ("sensitive_questions", "sensitive or legal"),
        ("verification_challenge", "CAPTCHA or MFA"),
    ):
        result = evaluate_and_reserve(
            db_session,
            candidate_id=candidate["id"],
            preparation_id=preparation.id,
            readiness=_failed(code),
            now=NOW,
        )
        assert result.permitted is False
        assert phrase in result.reasons[0]
        assert result.reservation_id is None


def test_authorized_local_form_submits_once_through_the_existing_click(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr("app.autofill.sessions.session_scope", _scope(db_session))
    monkeypatch.setattr("app.autofill.readiness.readiness_for_run", lambda run: _Ready())
    monkeypatch.setattr("app.autofill.sessions._plan_for", lambda run, html, url=None: type("Live", (), {"blockers": []})())
    candidate = _candidate(client, "ada.click@example.com")
    resume = _resume(db_session, candidate["id"])
    preparation, tracked = _application(db_session, candidate["id"], resume.id, external_id="click")
    saved = _enable(client, resume.id, max_per_day=2, max_per_session=2)
    playwright, browser, page = _page(SUCCESS)
    run = _run(preparation, candidate["id"], page)
    try:
        submitted = submit_session(run.id, confirm=False, preparation_id=preparation.id, apply_url=URL, grant=True)
        assert submitted.state == "submitted"
        assert submitted.phase == "submitted"
        assert page.evaluate("window.__clicks") == 1
        db_session.expire_all()
        stored = db_session.get(TrackedApplication, tracked.id)
        assert stored.status == ApplicationStatus.SUBMITTED
        event = db_session.scalar(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == tracked.id,
                ApplicationEvent.new_status == ApplicationStatus.SUBMITTING,
            )
        )
        assert event is not None
        assert event.initiation == "auto_apply"
        assert event.authorization_id is not None
        assert saved["active"] is True
        reservation = db_session.scalar(select(AutoApplyReservation).where(AutoApplyReservation.application_id == tracked.id))
        assert reservation.state == "settled"
        again = submit_session(run.id, confirm=False, preparation_id=preparation.id, apply_url=URL, grant=True)
        assert page.evaluate("window.__clicks") == 1
        assert "not requested" in again.message
        db_session.expire_all()
        assert db_session.get(TrackedApplication, tracked.id).status == ApplicationStatus.SUBMITTED
    finally:
        with _LOCK:
            _SESSIONS.pop(run.id, None)
        _close(playwright, browser)


def test_failure_and_unknown_outcomes_do_not_retry(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr("app.autofill.sessions.session_scope", _scope(db_session))
    monkeypatch.setattr("app.autofill.readiness.readiness_for_run", lambda run: _Ready())
    monkeypatch.setattr("app.autofill.sessions._plan_for", lambda run, html, url=None: type("Live", (), {"blockers": []})())
    candidate = _candidate(client, "ada.outcome@example.com")
    resume = _resume(db_session, candidate["id"])
    failed_prep, failed_row = _application(db_session, candidate["id"], resume.id, external_id="failed-click")
    _enable(client, resume.id, max_per_day=5, max_per_session=5)
    playwright, browser, page = _page(FAILURE)
    run = _run(failed_prep, candidate["id"], page)
    try:
        failed = submit_session(run.id, confirm=False, preparation_id=failed_prep.id, apply_url=URL, grant=True)
        assert failed.state == "submission_failed"
        assert failed.phase == "failed"
        assert page.evaluate("window.__clicks") == 1
        db_session.expire_all()
        assert db_session.get(TrackedApplication, failed_row.id).status == ApplicationStatus.SUBMISSION_FAILED
        run.auto_apply_armed = True
        run.auto_apply_used = False
        run.state = "filled_for_review"
        refused = evaluate_and_reserve(
            db_session, candidate_id=candidate["id"], preparation_id=failed_prep.id, readiness=_Ready(), now=datetime.now(timezone.utc)
        )
        assert refused.permitted is False
        assert page.evaluate("window.__clicks") == 1
    finally:
        with _LOCK:
            _SESSIONS.pop(run.id, None)
        _close(playwright, browser)

    unknown_prep, unknown_row = _application(db_session, candidate["id"], resume.id, external_id="unknown-click")
    playwright, browser, page = _page(SILENT)
    run = _run(unknown_prep, candidate["id"], page)
    try:
        unknown = submit_session(run.id, confirm=False, preparation_id=unknown_prep.id, apply_url=URL, grant=True)
        assert unknown.state == "confirmation_unknown"
        assert unknown.phase == "confirmation_unknown"
        assert page.evaluate("window.__clicks") == 1
        db_session.expire_all()
        assert db_session.get(TrackedApplication, unknown_row.id).status == ApplicationStatus.CONFIRMATION_UNKNOWN
        retry = evaluate_and_reserve(
            db_session,
            candidate_id=candidate["id"],
            preparation_id=unknown_prep.id,
            readiness=_Ready(),
            now=datetime.now(timezone.utc),
        )
        assert retry.permitted is False
        assert "unresolved" in retry.reasons[0]
        assert page.evaluate("window.__clicks") == 1
    finally:
        with _LOCK:
            _SESSIONS.pop(run.id, None)
        _close(playwright, browser)


def test_revoking_during_fill_and_a_closed_browser_do_not_click(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.auto_apply.now_utc", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr("app.autofill.sessions.session_scope", _scope(db_session))
    monkeypatch.setattr("app.autofill.readiness.readiness_for_run", lambda run: _Ready())
    monkeypatch.setattr("app.autofill.sessions._plan_for", lambda run, html, url=None: type("Live", (), {"blockers": []})())
    candidate = _candidate(client, "ada.revoke@example.com")
    resume = _resume(db_session, candidate["id"])
    preparation, tracked = _application(db_session, candidate["id"], resume.id, external_id="revoke")
    _enable(client, resume.id)
    client.put(
        "/api/candidate/auto-apply",
        json={
            "enabled": False,
            "acknowledge": False,
            "provider": "greenhouse",
            "job_categories": ["swe_backend"],
            "employment_types": ["internship"],
            "locations": ["Santa Cruz, CA"],
            "min_match_score": 70,
            "max_per_day": 2,
            "max_per_session": 2,
            "resume_ids": [resume.id],
            "expires_at": "2027-06-01T00:00:00Z",
        },
    )
    playwright, browser, page = _page(SUCCESS)
    run = _run(preparation, candidate["id"], page)
    try:
        paused = submit_session(run.id, confirm=False, preparation_id=preparation.id, apply_url=URL, grant=True)
        assert paused.state == "needs_review"
        assert page.evaluate("window.__clicks") == 0
        assert "off" in paused.message.casefold()
        db_session.expire_all()
        assert db_session.get(TrackedApplication, tracked.id).status == ApplicationStatus.NEEDS_REVIEW
    finally:
        with _LOCK:
            _SESSIONS.pop(run.id, None)
        _close(playwright, browser)

    class _Dead:
        def call(self, fn, timeout=90):
            raise TimeoutError()

    run = _run(preparation, candidate["id"], None)
    run._worker = _Dead()
    run.auto_apply_armed = True
    run.auto_apply_used = False
    run.state = "filled_for_review"
    tracked_again = db_session.get(TrackedApplication, tracked.id)
    tracked_again.status = ApplicationStatus.READY_TO_SUBMIT
    db_session.flush()
    try:
        interrupted = submit_session(run.id, confirm=False, preparation_id=preparation.id, apply_url=URL, grant=True)
        assert interrupted.state == "needs_review"
        assert "nothing was submitted" in interrupted.message.casefold()
    finally:
        with _LOCK:
            _SESSIONS.pop(run.id, None)


def test_review_confirmation_is_still_required(client):
    from app.core.local_auth import load_or_create_token
    from tests.unit.test_application_submission import _close_run, _open_run

    run = _open_run()
    headers = {"X-CareerPilot-Token": load_or_create_token()}
    try:
        denied = client.post(
            f"/api/autofill/sessions/{run.id}/submit",
            json={"confirm": False, "preparation_id": run.preparation_id, "apply_url": URL},
            headers=headers,
        )
        assert denied.status_code == 409
        assert "not confirmed" in denied.text
    finally:
        _close_run(run)


def test_concurrent_reservations_allow_only_one_when_one_slot_remains(test_engine):
    maker = sessionmaker(bind=test_engine, future=True)
    db = maker()
    token = uuid.uuid4().hex
    try:
        from app.models.candidate import Candidate
        from app.models.auto_apply import AutoApplyAuthorization

        candidate = Candidate(full_name="Grace Hopper", email=f"grace-{token}@example.com")
        db.add(candidate)
        db.flush()
        resume = _resume(db, candidate.id)
        first, _one = _application(db, candidate.id, resume.id, external_id=f"race-a-{token}")
        second, _two = _application(db, candidate.id, resume.id, external_id=f"race-b-{token}")
        grant = AutoApplyAuthorization(
            candidate_id=candidate.id,
            enabled=True,
            acknowledged=True,
            acknowledged_at=NOW,
            job_categories=[RoleCategory.SWE_BACKEND],
            employment_types=[EmploymentType.INTERNSHIP],
            locations=["Santa Cruz, CA"],
            min_match_score=70,
            max_per_day=1,
            max_per_session=2,
            resume_ids=[resume.id],
            expires_at=NOW + timedelta(days=30),
            session_started_at=NOW,
        )
        db.add(grant)
        db.commit()
        barrier = threading.Barrier(2)
        results = []

        def attempt(preparation_id):
            local = maker()
            try:
                barrier.wait(5)
                result = evaluate_and_reserve(
                    local,
                    candidate_id=candidate.id,
                    preparation_id=preparation_id,
                    readiness=_Ready(),
                    now=NOW + timedelta(minutes=5),
                )
                local.commit()
                results.append(result.permitted)
            finally:
                local.close()

        threads = [
            threading.Thread(target=attempt, args=(first.id,)),
            threading.Thread(target=attempt, args=(second.id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(results) == [False, True]
    finally:
        db.rollback()
        cleanup = maker()
        try:
            from sqlalchemy import delete

            from app.models.candidate import Candidate

            row = cleanup.scalar(select(Candidate).where(Candidate.email == f"grace-{token}@example.com"))
            if row is not None:
                cleanup.delete(row)
                cleanup.flush()
            employers = cleanup.scalars(select(Employer).where(Employer.name.like(f"%{token}"))).all()
            for employer in employers:
                source_ids = list(
                    cleanup.scalars(select(JobSource.id).where(JobSource.employer_id == employer.id)).all()
                )
                job_ids = list(
                    cleanup.scalars(select(Job.id).where(Job.job_source_id.in_(source_ids or [-1]))).all()
                )
                if job_ids:
                    cleanup.execute(delete(JobLocation).where(JobLocation.job_id.in_(job_ids)))
                    cleanup.execute(delete(JobAssessment).where(JobAssessment.job_id.in_(job_ids)))
                    cleanup.execute(delete(TrackedApplication).where(TrackedApplication.job_id.in_(job_ids)))
                    cleanup.execute(delete(Job).where(Job.id.in_(job_ids)))
                if source_ids:
                    cleanup.execute(delete(JobSource).where(JobSource.id.in_(source_ids)))
                cleanup.delete(employer)
            cleanup.commit()
        finally:
            cleanup.close()
            db.close()
