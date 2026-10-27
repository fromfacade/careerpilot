"""Application preparations: snapshot, idempotency, cancel. Not submission."""

from __future__ import annotations

import pytest

from app.ai.mock import MockAnswerProvider
from app.core.config import Settings
from app.models.enums import JobProvider
from app.models.job import Job
from app.models.job_source import Employer, JobSource

JD = """
Backend Engineer — Acme

Requirements:
- 2+ years of Python experience
- Experience with FastAPI or Django
- Authorized to work in the United States

Preferred:
- Redis
- PostgreSQL

Responsibilities:
- Build and operate backend services
"""


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
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.prep@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _job(db_session, description=JD):
    employer = Employer(name="Acme Prep")
    db_session.add(employer)
    db_session.flush()
    source = JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token="acme-prep")
    db_session.add(source)
    db_session.flush()
    job = Job(
        job_source_id=source.id,
        external_id="backend-1",
        title="Backend Engineer",
        description_text=description,
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/jobs/backend-1",
        content_hash="hash-backend-1",
        dedupe_key="acme prep|backend engineer|unspecified",
        raw_payload={"id": "backend-1"},
    )
    db_session.add(job)
    db_session.flush()
    return job


def test_prepare_snapshots_job_and_is_idempotent(client, db_session):
    _candidate(client)
    job = _job(db_session)
    first = client.post("/api/preparations", json={"job_id": job.id})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["state"] == "needs_review"
    assert body["snapshot_job_title"] == "Backend Engineer"
    assert body["snapshot_employer"] == "Acme Prep"
    assert "FastAPI" in body["snapshot_description"]
    assert body["snapshot_apply_url"] == "https://example.com/apply"
    assert "submit" not in body
    assert body["analysis"]["technologies"]
    assert "matched" in body["match_report"]
    assert "header" in body["tailored_resume"]
    assert body["design_limitation"]

    job.title = "Changed After Snapshot"
    job.description_text = "This later edit must not appear in the snapshot."
    db_session.flush()

    second = client.post("/api/preparations", json={"job_id": job.id})
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]
    assert second.json()["snapshot_job_title"] == "Backend Engineer"
    assert "FastAPI" in second.json()["snapshot_description"]
    assert "later edit" not in second.json()["snapshot_description"]


def test_cancel_allows_a_new_preparation(client, db_session):
    _candidate(client)
    job = _job(db_session)
    first = client.post("/api/preparations", json={"job_id": job.id})
    cancelled = client.post(f"/api/preparations/{first.json()['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201
    assert created.json()["id"] != first.json()["id"]
    listing = client.get("/api/preparations")
    assert {row["state"] for row in listing.json()} == {"cancelled", "needs_review"}


def test_prepare_reuses_approved_answers_and_skips_sensitive(client, db_session):
    _candidate(client)
    job = _job(db_session)
    approved = client.post(
        "/api/candidate/answers",
        json={
            "question": "Tell us about a project you are proud of.",
            "answer_text": "I built Alpha Queue in FastAPI.",
            "category": "experience",
            "status": "approved",
        },
    )
    assert approved.status_code == 201
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    answers = created.json()["answers"]
    reused = next(item for item in answers if "project" in item["question"].lower())
    assert reused["origin"] == "reused"
    assert reused["answer_text"] == "I built Alpha Queue in FastAPI."
    assert reused["source_answer_id"] == approved.json()["id"]
    generated = next(item for item in answers if "interested" in item["question"].lower())
    assert generated["origin"] == "generated"
    sensitive = next(item for item in answers if item["is_sensitive"])
    assert sensitive["answer_text"] == ""
    assert sensitive["status"] == "needs_review"
    kept = client.get(f"/api/candidate/answers/{approved.json()['id']}").json()
    assert kept["answer_text"] == "I built Alpha Queue in FastAPI."
    assert kept["status"] == "approved"


def test_prepare_survives_ai_failure(client, db_session, monkeypatch):
    from app.core.exceptions import AIProviderError

    _candidate(client)
    job = _job(db_session)

    def boom(settings=None):
        raise AIProviderError("upstream", "Gemini returned HTTP 500.")

    monkeypatch.setattr("app.services.preparation_service.get_provider", boom)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201
    assert created.json()["analysis"]["summary"]
    assert created.json()["tailored_resume"]["header"]
    assert created.json()["answers"]
    assert all("500" in " ".join(item["missing_information"]) or item["origin"] == "reused" or item["is_sensitive"] for item in created.json()["answers"])


def test_missing_job_or_empty_description_is_rejected(client, db_session):
    _candidate(client)
    assert client.post("/api/preparations", json={"job_id": 99999}).status_code == 404
    job = _job(db_session, description="   ")
    empty = client.post("/api/preparations", json={"job_id": job.id})
    assert empty.status_code == 422
