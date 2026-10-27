"""Answer library API: CRUD, duplicates, preferred, sensitive review, fact links."""

from __future__ import annotations


def _candidate(client):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.answers@example.com"})
    assert resp.status_code == 201
    return resp.json()


def test_create_edit_search_and_delete_answer(client):
    _candidate(client)
    created = client.post(
        "/api/candidate/answers",
        json={
            "question": "Why are you interested in this position?",
            "answer_text": "I want to build reliable backend systems.",
            "category": "interest",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["origin"] == "manual"
    assert body["is_sensitive"] is False
    assert body["is_reusable"] is True

    edited = client.patch(
        f"/api/candidate/answers/{body['id']}",
        json={"answer_text": "I want to build reliable backend systems at scale.", "status": "approved"},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "approved"

    found = client.get("/api/candidate/answers", params={"search": "reliable", "category": "interest"})
    assert [row["id"] for row in found.json()] == [body["id"]]

    deleted = client.delete(f"/api/candidate/answers/{body['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/candidate/answers").json() == []


def test_equivalent_question_and_answer_is_rejected(client):
    _candidate(client)
    payload = {
        "question": "Why are you interested in this position?",
        "answer_text": "I like the team's work on infrastructure.",
        "category": "interest",
    }
    assert client.post("/api/candidate/answers", json=payload).status_code == 201
    again = client.post(
        "/api/candidate/answers",
        json={**payload, "question": "why are you interested in this position"},
    )
    assert again.status_code == 409

    variant = client.post(
        "/api/candidate/answers",
        json={**payload, "answer_text": "A shorter version for internship forms."},
    )
    assert variant.status_code == 201
    listed = client.get("/api/candidate/answers").json()
    assert len(listed) == 2


def test_only_one_preferred_answer_per_question(client):
    _candidate(client)
    first = client.post(
        "/api/candidate/answers",
        json={
            "question": "Tell us about a project you are proud of.",
            "answer_text": "Alpha Queue.",
            "category": "experience",
            "is_preferred": True,
        },
    )
    second = client.post(
        "/api/candidate/answers",
        json={
            "question": "Tell us about a project you are proud of.",
            "answer_text": "Beta Relay, for safety work.",
            "category": "experience",
            "is_preferred": True,
        },
    )
    assert first.status_code == 201 and second.status_code == 201
    listed = {row["id"]: row for row in client.get("/api/candidate/answers").json()}
    assert listed[first.json()["id"]]["is_preferred"] is False
    assert listed[second.json()["id"]]["is_preferred"] is True


def test_sensitive_answers_cannot_skip_review(client):
    _candidate(client)
    created = client.post(
        "/api/candidate/answers",
        json={
            "question": "Are you authorized to work in the United States?",
            "answer_text": "Yes, I am a U.S. citizen.",
            "category": "work_authorization",
            "status": "approved",
        },
    )
    assert created.status_code == 422

    draft = client.post(
        "/api/candidate/answers",
        json={
            "question": "Are you authorized to work in the United States?",
            "answer_text": "Yes, I am a U.S. citizen.",
            "category": "work_authorization",
        },
    )
    assert draft.status_code == 201
    assert draft.json()["is_sensitive"] is True
    assert draft.json()["status"] == "draft"

    skipped = client.patch(f"/api/candidate/answers/{draft.json()['id']}", json={"status": "approved"})
    assert skipped.status_code == 422

    reviewed = client.patch(f"/api/candidate/answers/{draft.json()['id']}", json={"status": "reviewed"})
    assert reviewed.status_code == 200
    approved = client.patch(f"/api/candidate/answers/{draft.json()['id']}", json={"status": "approved"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_prefer_not_to_answer_clears_text(client):
    _candidate(client)
    created = client.post(
        "/api/candidate/answers",
        json={
            "question": "Do you have a disability?",
            "category": "disability",
            "prefer_not_to_answer": True,
            "answer_text": "this should be discarded",
        },
    )
    assert created.status_code == 201
    assert created.json()["prefer_not_to_answer"] is True
    assert created.json()["answer_text"] == ""
    assert created.json()["is_sensitive"] is True


def test_answer_can_link_only_verified_canonical_facts(client):
    _candidate(client)
    unverified = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "project", "fact_key": "Alpha", "fact_value": {"name": "Alpha"}},
    )
    assert unverified.status_code == 201
    refused = client.post(
        "/api/candidate/answers",
        json={
            "question": "Describe a project.",
            "answer_text": "I built Alpha.",
            "category": "experience",
            "canonical_fact_ids": [unverified.json()["id"]],
        },
    )
    assert refused.status_code == 422

    client.patch(
        f"/api/candidate/canonical-facts/{unverified.json()['id']}",
        json={"verification_status": "verified"},
    )
    ok = client.post(
        "/api/candidate/answers",
        json={
            "question": "Describe a project.",
            "answer_text": "I built Alpha.",
            "category": "experience",
            "canonical_fact_ids": [unverified.json()["id"]],
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["fact_links"][0]["canonical_fact_id"] == unverified.json()["id"]
