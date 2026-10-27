"""Persistent application records. These tests never open or submit a browser form."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import TrackedApplication
from app.models.enums import ApplicationStatus, JobProvider
from app.models.job import Job
from app.models.job_source import Employer, JobSource
from app.models.preparation import ApplicationPreparation
from app.services.application_tracking import (
    apply_readiness,
    count_for_job,
    ensure_for_preparation,
    get_application_or_404,
    transition,
)
from app.ai.mock import MockAnswerProvider


JD = "Backend Engineer. Build services with Python."


@pytest.fixture(autouse=True)
def mock_preparation_ai(monkeypatch):
    monkeypatch.setattr(
        "app.services.preparation_service.get_provider",
        lambda settings=None: MockAnswerProvider("I want to build backend systems."),
    )
    monkeypatch.setattr(
        "app.services.preparation_service.get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="mock", ai_model="mock"),
    )


def _candidate(client):
    resp = client.post("/api/candidate", json={"full_name": "Ada Lovelace", "email": "ada.tracking@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _job(db_session, external_id="track-1"):
    employer = Employer(name="Northwind Tracking")
    db_session.add(employer)
    db_session.flush()
    source = JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token=f"track-{external_id}")
    db_session.add(source)
    db_session.flush()
    job = Job(
        job_source_id=source.id,
        external_id=external_id,
        title="Backend Intern",
        description_text=JD,
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/jobs/track",
        content_hash=f"hash-{external_id}",
        dedupe_key=f"northwind|{external_id}",
        raw_payload={"id": external_id},
    )
    db_session.add(job)
    db_session.flush()
    return job


def _prepare(client, db_session):
    candidate = _candidate(client)
    job = _job(db_session)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    return candidate, job, created.json()


class _Check:
    def __init__(self, code, status, detail):
        self.code = code
        self.status = status
        self.detail = detail


class _Readiness:
    def __init__(self, status, checks):
        self.status = status
        self.checks = checks


def test_preparation_creates_one_persistent_record(client, db_session):
    _candidate_body, job, prep = _prepare(client, db_session)
    assert prep["application_status"] == "preparing"
    listed = client.get("/api/applications")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    row = body[0]
    assert row["job_id"] == job.id
    assert row["employer"] == "Northwind Tracking"
    assert row["preparation_id"] == prep["id"]
    assert row["status"] == "preparing"
    assert row["submitted_at"] is None
    assert row["confirmation"] is None
    assert row["failure_reason"] is None
    assert "answer" not in row
    again = client.post("/api/preparations", json={"job_id": job.id})
    assert again.status_code == 200
    assert again.json()["application_id"] == prep["application_id"]
    assert count_for_job(db_session, prep["candidate_id"], job.id) == 1

    db_session.expire_all()
    stored = db_session.get(TrackedApplication, prep["application_id"])
    assert stored is not None
    assert stored.status == ApplicationStatus.PREPARING
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_readiness_updates_status_without_storing_personal_answers(client, db_session):
    _candidate_body, job, prep = _prepare(client, db_session)
    updated = apply_readiness(
        db_session,
        candidate_id=prep["candidate_id"],
        preparation_id=prep["id"],
        readiness=_Readiness(
            "needs_review",
            [_Check("required_fields", "needs_review", "Email ada.tracking@example.com was not filled. Call +1 555 010 0199.")],
        ),
    )
    assert updated.status == ApplicationStatus.NEEDS_REVIEW
    assert "ada.tracking@example.com" not in (updated.failure_reason or "")
    assert "555" not in (updated.failure_reason or "")
    assert updated.confirmation is None
    assert updated.submitted_at is None

    ready = apply_readiness(
        db_session,
        candidate_id=prep["candidate_id"],
        preparation_id=prep["id"],
        readiness=_Readiness("ready_to_submit", [_Check("required_fields", "passed", "Filled.")]),
    )
    assert ready.status == ApplicationStatus.READY_TO_SUBMIT
    assert ready.failure_reason is None
    fetched = client.get(f"/api/applications/{ready.id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ready_to_submit"
    assert count_for_job(db_session, prep["candidate_id"], job.id) == 1


def test_invalid_and_locked_transitions(client, db_session):
    _candidate_body, _job, prep = _prepare(client, db_session)
    row = get_application_or_404(db_session, prep["candidate_id"], prep["application_id"])
    with pytest.raises(ValidationError):
        transition(row, ApplicationStatus.SUBMITTED)
    with pytest.raises(ValidationError):
        transition(row, ApplicationStatus.SUBMITTING)
    transition(row, ApplicationStatus.NEEDS_REVIEW, failure_reason="Phone has not been filled yet.")
    transition(row, ApplicationStatus.READY_TO_SUBMIT)
    transition(row, ApplicationStatus.SUBMITTING)
    done = transition(
        row,
        ApplicationStatus.SUBMITTED,
        confirmation="Thank you for applying. A note was sent to ada@example.com.",
        submitted_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
    )
    db_session.commit()
    assert done.submitted_at is not None
    assert "ada@example.com" not in (done.confirmation or "")
    with pytest.raises(ValidationError):
        transition(done, ApplicationStatus.PREPARING)
    kept = apply_readiness(
        db_session,
        candidate_id=prep["candidate_id"],
        preparation_id=prep["id"],
        readiness=_Readiness("needs_review", [_Check("required_fields", "needs_review", "Still open.")]),
    )
    assert kept.status == ApplicationStatus.SUBMITTED


def test_confirmation_unknown_is_not_retried_as_submitting(client, db_session):
    _candidate_body, _job, prep = _prepare(client, db_session)
    row = get_application_or_404(db_session, prep["candidate_id"], prep["application_id"])
    transition(row, ApplicationStatus.READY_TO_SUBMIT)
    transition(row, ApplicationStatus.SUBMITTING)
    transition(row, ApplicationStatus.CONFIRMATION_UNKNOWN, confirmation="The page did not say whether it was received.")
    with pytest.raises(ValidationError):
        transition(row, ApplicationStatus.SUBMITTING)
    with pytest.raises(ValidationError):
        apply_readiness(
            db_session,
            candidate_id=prep["candidate_id"],
            preparation_id=prep["id"],
            readiness=_Readiness("submitted", []),
        )


def test_missing_job_and_preparation(client, db_session):
    candidate = _candidate(client)
    missing = client.get("/api/applications/999999")
    assert missing.status_code == 404
    with pytest.raises(NotFoundError):
        apply_readiness(
            db_session,
            candidate_id=candidate["id"],
            preparation_id=999999,
            readiness=_Readiness("needs_review", []),
        )
    orphan = ApplicationPreparation(
        candidate_id=candidate["id"],
        job_id=None,
        snapshot_job_title="Orphan role",
        snapshot_employer="Nowhere",
        snapshot_description="No job row.",
    )
    db_session.add(orphan)
    db_session.commit()
    with pytest.raises(NotFoundError):
        ensure_for_preparation(db_session, orphan)
