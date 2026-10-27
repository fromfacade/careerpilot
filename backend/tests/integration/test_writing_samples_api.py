"""Writing samples: CRUD, duplicates, authentic vs adopted, never AI origin."""

from __future__ import annotations


def _candidate(client):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.samples@example.com"})
    assert resp.status_code == 201
    return resp.json()


def test_create_edit_approve_and_delete_sample(client):
    _candidate(client)
    created = client.post(
        "/api/candidate/writing-samples",
        json={
            "title": "Internship note",
            "body": "I built a FastAPI service that queued jobs with Redis.",
            "category": "technical_experience",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["origin"] == "user_written"
    assert body["is_approved_style_reference"] is False

    edited = client.patch(
        f"/api/candidate/writing-samples/{body['id']}",
        json={"is_approved_style_reference": True, "title": "Queue service"},
    )
    assert edited.status_code == 200
    assert edited.json()["is_approved_style_reference"] is True
    assert edited.json()["title"] == "Queue service"

    approved = client.get("/api/candidate/writing-samples", params={"approved_only": True})
    assert [row["id"] for row in approved.json()] == [body["id"]]

    deleted = client.delete(f"/api/candidate/writing-samples/{body['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/candidate/writing-samples").json() == []


def test_duplicate_and_short_samples_are_rejected(client):
    _candidate(client)
    payload = {"body": "I built a FastAPI service that queued jobs with Redis."}
    assert client.post("/api/candidate/writing-samples", json=payload).status_code == 201
    dup = client.post("/api/candidate/writing-samples", json=payload)
    assert dup.status_code == 409
    short = client.post("/api/candidate/writing-samples", json={"body": "Too short"})
    assert short.status_code == 422


def test_ai_drafts_are_not_auto_classified_as_user_writing(client, db_session):
    _candidate(client)
    answer = client.post(
        "/api/candidate/answers",
        json={
            "question": "Tell us about a project you are proud of.",
            "answer_text": "I built Alpha Queue, a FastAPI worker that retried failed jobs.",
            "category": "experience",
        },
    )
    assert answer.status_code == 201
    from app.models.answer import ApplicationAnswer
    from app.models.enums import AnswerOrigin

    row = db_session.get(ApplicationAnswer, answer.json()["id"])
    assert row is not None
    row.origin = AnswerOrigin.AI_DRAFT
    db_session.flush()

    adopted = client.post(
        "/api/candidate/writing-samples",
        json={"source_answer_id": answer.json()["id"], "category": "technical_experience"},
    )
    assert adopted.status_code == 201, adopted.text
    body = adopted.json()
    assert body["origin"] == "adopted_from_answer"
    assert body["origin"] != "ai_draft"
    assert "Alpha Queue" in body["body"]
    assert body["source_answer_id"] == answer.json()["id"]

    invalid = client.post(
        "/api/candidate/writing-samples",
        json={"body": "I wrote this sample about backend work myself.", "origin": "ai_draft"},
    )
    assert invalid.status_code == 422


def test_adopted_sample_survives_answer_delete(client):
    _candidate(client)
    answer = client.post(
        "/api/candidate/answers",
        json={
            "question": "Why this role?",
            "answer_text": "I want to work on backend systems that stay up.",
            "category": "interest",
        },
    )
    adopted = client.post(
        "/api/candidate/writing-samples",
        json={"source_answer_id": answer.json()["id"], "category": "motivation"},
    )
    assert adopted.status_code == 201
    assert client.delete(f"/api/candidate/answers/{answer.json()['id']}").status_code == 204
    remaining = client.get("/api/candidate/writing-samples").json()
    assert remaining[0]["id"] == adopted.json()["id"]
    assert remaining[0]["source_answer_id"] is None
