"""Application preparations: snapshot, idempotency, cancel. Not submission."""

from __future__ import annotations

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


def test_missing_job_or_empty_description_is_rejected(client, db_session):
    _candidate(client)
    assert client.post("/api/preparations", json={"job_id": 99999}).status_code == 404
    job = _job(db_session, description="   ")
    empty = client.post("/api/preparations", json={"job_id": job.id})
    assert empty.status_code == 422
