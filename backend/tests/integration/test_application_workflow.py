"""The job-listing workflow reuses preparation and never submits by itself."""

from __future__ import annotations

import pytest

from app.ai.mock import MockAnswerProvider
from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.models.enums import ApplicationStatus, Eligibility, JobProvider, Relevance
from app.models.job import Job, JobAssessment
from app.models.job_source import Employer, JobSource
from app.services.application_tracking import claim_for_submission, get_application_or_404, transition
from app.services.application_workflow import begin_workflow


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
    resp = client.post("/api/candidate", json={"full_name": "Ada Lovelace", "email": "ada.workflow@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _job(db_session, *, provider: JobProvider, external_id: str, apply_url: str, employer_name: str):
    employer = Employer(name=employer_name)
    db_session.add(employer)
    db_session.flush()
    source = JobSource(employer_id=employer.id, provider=provider, board_token="northwind")
    db_session.add(source)
    db_session.flush()
    job = Job(
        job_source_id=source.id,
        external_id=external_id,
        title="Backend Intern",
        description_text="Backend Engineer. Build services with Python.",
        apply_url=apply_url,
        canonical_url=apply_url,
        content_hash=f"hash-{external_id}",
        dedupe_key=f"{employer_name}|{external_id}",
        raw_payload={"id": external_id},
    )
    db_session.add(job)
    db_session.flush()
    return job


def test_workflow_reuses_one_preparation_and_does_not_submit(client, db_session):
    candidate = _candidate(client)
    job = _job(
        db_session,
        provider=JobProvider.GREENHOUSE,
        external_id="12345",
        apply_url="https://example.com/jobs/12345",
        employer_name="Northwind Workflow",
    )
    db_session.add(
        JobAssessment(
            job_id=job.id,
            candidate_id=candidate["id"],
            eligibility=Eligibility.UNKNOWN,
            eligibility_reasons=[{"rule": "graduation_timing", "result": "unknown", "detail": "The posting does not state a graduation date."}],
            relevance=Relevance.UNKNOWN,
            relevance_reasons=[],
            match_score=0,
            match_reasons=[],
        )
    )
    db_session.commit()
    first = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["reused"] is False
    assert body["can_open_browser"] is True
    assert body["eligibility"] == "unknown"
    assert body["mode"] == "review"
    assert "not" in body["eligibility_detail"].casefold() or "unknown" in body["message"].casefold()
    assert body["preparation"]["application_status"] == "preparing"
    assert "No approved resume" in body["message"]
    assert body["preparation"]["selected_resume_name"] is None
    second = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["preparation"]["id"] == body["preparation"]["id"]
    listed = client.get("/api/preparations")
    assert len(listed.json()) == 1
    assert listed.json()[0]["application_status"] != "submitted"


def test_unsupported_boards_do_not_start_an_application(client, db_session):
    _candidate(client)
    job = _job(
        db_session,
        provider=JobProvider.LEVER,
        external_id="lever-1",
        apply_url="https://jobs.lever.co/northwind/lever-1",
        employer_name="Lever Workflow",
    )
    db_session.commit()
    response = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert response.status_code == 409
    assert "Lever" in response.text
    assert "submit" in response.text.casefold()
    assert client.get("/api/preparations").json() == []


def test_received_and_unknown_applications_do_not_open_again(client, db_session):
    candidate = _candidate(client)
    job = _job(
        db_session,
        provider=JobProvider.GREENHOUSE,
        external_id="67890",
        apply_url="https://boards.greenhouse.io/northwind/jobs/67890",
        employer_name="Received Workflow",
    )
    db_session.commit()
    started = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert started.status_code == 200
    prep = started.json()["preparation"]
    row = get_application_or_404(db_session, candidate["id"], prep["application_id"])
    transition(row, ApplicationStatus.READY_TO_SUBMIT)
    transition(row, ApplicationStatus.SUBMITTING)
    transition(row, ApplicationStatus.CONFIRMATION_UNKNOWN, confirmation="The page did not show a receipt.")
    db_session.commit()
    unknown = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert unknown.status_code == 200
    assert unknown.json()["can_open_browser"] is False
    assert "unknown" in unknown.json()["message"].casefold()
    transition(db_session.get(type(row), row.id), ApplicationStatus.SUBMISSION_FAILED, failure_reason="The user saw the form still open.")
    db_session.commit()
    failed = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert failed.status_code == 200
    assert failed.json()["can_open_browser"] is True
    row = get_application_or_404(db_session, candidate["id"], prep["application_id"])
    transition(row, ApplicationStatus.READY_TO_SUBMIT)
    transition(row, ApplicationStatus.SUBMITTING)
    transition(row, ApplicationStatus.SUBMITTED, confirmation="The employer page confirmed receipt.")
    db_session.commit()
    again = client.post("/api/preparations/workflow", json={"job_id": job.id})
    assert again.status_code == 200
    assert again.json()["can_open_browser"] is False
    assert again.json()["preparation"]["application_status"] == "submitted"
    with pytest.raises(ValidationError, match="already submitted"):
        claim_for_submission(db_session, candidate_id=candidate["id"], preparation_id=prep["id"])
