"""Grounded draft generation: verified facts only, sensitive questions refused."""

from __future__ import annotations

import pytest

from app.ai.mock import MockAnswerProvider
from app.core.config import Settings
from app.core.exceptions import AIProviderError


@pytest.fixture()
def mock_provider(monkeypatch):
    provider = MockAnswerProvider("I built Alpha Queue using FastAPI.")
    monkeypatch.setattr("app.services.generation_service.get_provider", lambda settings=None: provider)
    monkeypatch.setattr(
        "app.api.answers.get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="mock", gemini_api_key=""),
    )
    return provider


def _candidate(client):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.gen@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _verified_project(client, name="Alpha Queue"):
    created = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "project", "fact_key": name, "fact_value": {"name": name, "technologies": ["FastAPI"]}},
    )
    assert created.status_code == 201
    client.patch(
        f"/api/candidate/canonical-facts/{created.json()['id']}",
        json={"verification_status": "verified"},
    )
    return created.json()["id"]


def test_generate_uses_verified_facts_and_creates_a_draft(client, mock_provider):
    _candidate(client)
    fact_id = _verified_project(client)
    unverified = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "project", "fact_key": "Secret", "fact_value": {"name": "Secret", "bullets": ["Classified."]}}
    )
    assert unverified.status_code == 201

    resp = client.post(
        "/api/candidate/answers/generate",
        json={"question": "Tell us about a project you are proud of.", "category": "experience"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["origin"] == "ai_draft"
    assert body["status"] == "draft"
    assert body["answer_text"] == "I built Alpha Queue using FastAPI."
    assert [link["canonical_fact_id"] for link in body["fact_links"]] == [fact_id]
    assert unverified.json()["id"] not in [link["canonical_fact_id"] for link in body["fact_links"]]
    assert mock_provider.calls
    assert "Secret" not in mock_provider.calls[0].facts_block
    assert "Alpha Queue" in mock_provider.calls[0].facts_block


def test_generate_records_missing_information_when_no_facts_match(client, mock_provider):
    _candidate(client)
    resp = client.post(
        "/api/candidate/answers/generate",
        json={"question": "Tell us about a project you are proud of.", "category": "experience"},
    )
    assert resp.status_code == 201
    missing = resp.json()["missing_information"]
    assert missing
    assert any("project" in item for item in missing)


def test_sensitive_questions_never_call_the_provider(client, mock_provider):
    _candidate(client)
    resp = client.post(
        "/api/candidate/answers/generate",
        json={"question": "Are you authorized to work in the United States?", "category": "work_authorization"},
    )
    assert resp.status_code == 422
    assert "not drafted" in resp.json()["detail"]
    assert mock_provider.calls == []
    assert client.get("/api/candidate/answers").json() == []


def test_provider_failure_does_not_create_an_answer(client, monkeypatch):
    _candidate(client)

    def boom(settings=None):
        raise AIProviderError("timeout", "Gemini request failed after 2 attempts")

    monkeypatch.setattr("app.services.generation_service.get_provider", boom)
    monkeypatch.setattr(
        "app.api.answers.get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="gemini", gemini_api_key="x"),
    )
    resp = client.post(
        "/api/candidate/answers/generate",
        json={"question": "Why this role?", "category": "interest"},
    )
    assert resp.status_code == 503
    assert client.get("/api/candidate/answers").json() == []
    assert "x" not in resp.text
