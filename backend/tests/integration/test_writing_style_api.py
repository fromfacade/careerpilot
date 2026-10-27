"""Writing style profile: defaults, updates, and one-row-per-candidate."""

from __future__ import annotations

from app.services.writing_style_service import DEFAULT_INSTRUCTIONS, DEFAULT_PHRASES_TO_AVOID


def _candidate(client):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.style@example.com"})
    assert resp.status_code == 201
    return resp.json()


def test_get_creates_editable_defaults(client):
    _candidate(client)
    first = client.get("/api/candidate/writing-style")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["tone"] == "professional_conversational"
    assert body["formality"] == "medium"
    assert body["preferred_length"] == "short_medium"
    assert body["sentence_complexity"] == "moderate"
    assert body["technical_detail"] == "specific"
    assert body["vocabulary"] == "straightforward"
    assert body["phrases_to_avoid"] == DEFAULT_PHRASES_TO_AVOID
    assert body["additional_instructions"] == DEFAULT_INSTRUCTIONS

    second = client.get("/api/candidate/writing-style")
    assert second.json()["id"] == body["id"]


def test_update_persists_preferences(client):
    _candidate(client)
    updated = client.put(
        "/api/candidate/writing-style",
        json={
            "tone": "conversational",
            "formality": "low",
            "preferred_length": "short",
            "phrases_to_avoid": ["leverage", "leverage", "robust"],
            "additional_instructions": "Be direct.",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["tone"] == "conversational"
    assert body["formality"] == "low"
    assert body["preferred_length"] == "short"
    assert body["phrases_to_avoid"] == ["leverage", "robust"]
    assert body["additional_instructions"] == "Be direct."
    assert client.get("/api/candidate/writing-style").json()["tone"] == "conversational"


def test_writing_style_requires_a_candidate(client):
    resp = client.get("/api/candidate/writing-style")
    assert resp.status_code == 404
