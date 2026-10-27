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
    assert body["has_tailored_resume"] is False
    assert body["resume_selection_source"] == "none"
    assert "approved" in body["resume_selection_reason"].lower()

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
    assert created.json()["has_tailored_resume"] is False
    assert created.json()["answers"]
    assert all(
        "500" in " ".join(item["missing_information"])
        or "verified knowledge base" in " ".join(item["missing_information"])
        or item["origin"] == "reused"
        or item["is_sensitive"]
        for item in created.json()["answers"]
    )


STRIPE_JD = """
About Stripe Stripe is a financial infrastructure platform for businesses. Millions of companies from startups to Fortune 500s use Stripe to accept payments. Our internal stack includes Python, React, and Ruby used to process payments.
What you’ll do Work with senior engineers to design and implement backend services.
Minimum requirements Currently pursuing a BA/BS in Computer Science or a related field. Experience with at least one of Python, Java, or JavaScript.
Preferred qualifications Familiarity with Go.
Benefits Inclusive healthcare coverage and paid time off.
"""


def _verified_project(client, name="Alpha Queue"):
    created = client.post(
        "/api/candidate/canonical-facts",
        json={
            "fact_type": "project",
            "fact_key": name,
            "fact_value": {"name": name, "technologies": ["FastAPI", "Python"], "bullets": ["Queued jobs."]},
        },
    )
    assert created.status_code == 201
    client.patch(
        f"/api/candidate/canonical-facts/{created.json()['id']}",
        json={"verification_status": "verified"},
    )


def test_stripe_preparation_keeps_marketing_out_of_matches(client, db_session):
    _candidate(client)
    _verified_project(client)
    job = _job(db_session, description=STRIPE_JD)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    body = created.json()
    required = " ".join(item["text"] for item in body["analysis"]["required"]).lower()
    matched = " ".join(item["text"] for item in body["match_report"]["matched"]).lower()
    assert body["analysis"]["required"]
    assert "computer science" in required or "python" in required
    assert "fortune 500" not in required
    assert "fortune 500" not in matched
    assert "financial infrastructure" not in matched
    go = [item for item in body["match_report"]["uncertain"] if "go" in item["text"].lower()]
    assert go
    assert not any("go" in item["text"].lower() for item in body["match_report"]["missing"])


def test_interest_drafts_receive_employer_context_and_experience(client, db_session, monkeypatch):
    provider = MockAnswerProvider("I built Alpha Queue and want to work on backend services.")
    monkeypatch.setattr("app.services.preparation_service.get_provider", lambda settings=None: provider)
    _candidate(client)
    _verified_project(client)
    job = _job(db_session, description=STRIPE_JD)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    interest_calls = [call for call in provider.calls if "interested" in call.question.lower() or "work for" in call.question.lower()]
    assert interest_calls
    block = interest_calls[0].facts_block
    assert "Alpha Queue" in block
    assert "Stripe" in block or "Acme Prep" in block
    assert "backend services" in block.lower()
    assert "do not invent" in interest_calls[0].system_instruction.lower()


def test_unknown_skill_answer_needs_user_input_and_blocks_ready(client, db_session):
    _candidate(client)
    job = _job(db_session, description=STRIPE_JD)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    prep = created.json()
    skill = next(item for item in prep["answers"] if "experience with" in item["question"].lower())
    assert skill["answer_text"] == ""
    assert skill["status"] == "needs_review"
    assert any("not in your verified knowledge base" in note for note in skill["missing_information"])
    blocked = client.patch(
        f"/api/preparations/{prep['id']}/answers/{skill['id']}",
        json={"status": "approved"},
    )
    assert blocked.status_code == 422
    edited = client.patch(
        f"/api/preparations/{prep['id']}/answers/{skill['id']}",
        json={"answer_text": "I have coursework in JavaScript, not production work.", "status": "approved"},
    )
    assert edited.status_code == 200
    assert edited.json()["state"] != "ready"


def test_prepares_with_selected_resume_and_optional_tailor(client, db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    overridden = get_settings().model_copy(update={"resume_storage_dir": str(tmp_path / "resumes")})
    monkeypatch.setattr("app.api.resumes.get_settings", lambda: overridden)
    _candidate(client)
    from tests.integration.test_resumes_api import _SAMPLE_RESUME_TEXT, _build_minimal_pdf

    uploaded = client.post(
        "/api/resumes",
        files={"file": ("backend.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")},
    )
    assert uploaded.status_code == 201
    resume_id = uploaded.json()["resume"]["id"]
    client.patch(
        f"/api/resumes/{resume_id}",
        json={"profile_name": "Backend SWE Resume", "category": "backend", "is_approved": True, "focus_areas": ["FastAPI"]},
    )
    job = _job(db_session)
    created = client.post("/api/preparations", json={"job_id": job.id})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_resume_id"] == resume_id
    assert body["selected_resume_name"] == "Backend SWE Resume"
    assert body["has_tailored_resume"] is False
    assert body["resume_selection_source"] in {"automatic", "fallback_default"}
    assert "Backend SWE Resume" in body["resume_selection_reason"] or body["resume_selection_reason"]

    selected_id = body["source_resume_id"]
    regenerated = client.post(f"/api/preparations/{body['id']}/regenerate")
    assert regenerated.status_code == 200
    assert regenerated.json()["source_resume_id"] == selected_id

    tailored = client.post(f"/api/preparations/{body['id']}/tailor")
    assert tailored.status_code == 200, tailored.text
    assert tailored.json()["has_tailored_resume"] is True
    assert tailored.json()["source_resume_id"] == selected_id
    assert tailored.json()["tailored_resume"]["header"]

    reverted = client.post(f"/api/preparations/{body['id']}/tailor/revert")
    assert reverted.json()["has_tailored_resume"] is False
    assert reverted.json()["source_resume_id"] == selected_id


def test_missing_job_or_empty_description_is_rejected(client, db_session):
    _candidate(client)
    assert client.post("/api/preparations", json={"job_id": 99999}).status_code == 404
    job = _job(db_session, description="   ")
    empty = client.post("/api/preparations", json={"job_id": job.id})
    assert empty.status_code == 422
