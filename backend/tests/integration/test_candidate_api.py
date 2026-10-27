"""Integration tests for the candidate profile + preferences API.

Run against the real careerpilot_test PostgreSQL database with real
migrations applied (see tests/conftest.py).
"""

from __future__ import annotations


def test_get_candidate_returns_null_when_none_exists(client):
    resp = client.get("/api/candidate")
    assert resp.status_code == 200
    assert resp.json() is None


def test_create_candidate_persists_and_reads_back(client):
    payload = {
        "full_name": "Luis Castellanos",
        "email": "luis@example.com",
        "school": "UC Santa Cruz",
        "degree_level": "bachelors",
        "major": "Computer Science",
        "graduation_date": "2027-12-01",
        "graduation_date_precision": "month",
        "work_authorization_status": "us_citizen",
        "requires_sponsorship": "no",
    }
    create_resp = client.post("/api/candidate", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["full_name"] == "Luis Castellanos"
    assert body["degree_level"] == "bachelors"
    assert body["id"] > 0

    get_resp = client.get("/api/candidate")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "luis@example.com"


def test_create_candidate_twice_returns_409(client):
    payload = {"full_name": "A", "email": "a@example.com"}
    first = client.post("/api/candidate", json=payload)
    assert first.status_code == 201

    second = client.post("/api/candidate", json={"full_name": "B", "email": "b@example.com"})
    assert second.status_code == 409


def test_update_candidate_without_existing_profile_returns_404(client):
    resp = client.patch("/api/candidate", json={"full_name": "Someone"})
    assert resp.status_code == 404


def test_patch_candidate_partial_update(client):
    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis2@example.com"})

    resp = client.patch("/api/candidate", json={"school": "UC Santa Cruz"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["school"] == "UC Santa Cruz"
    assert body["full_name"] == "Luis"  # untouched fields preserved


def test_country_and_location_round_trip(client):
    created = client.post("/api/candidate", json={"full_name": "Ada Lovelace", "email": "ada.place@example.com"})
    assert created.status_code == 201
    assert created.json()["country"] is None
    assert created.json()["current_location"] is None

    saved = client.patch(
        "/api/candidate",
        json={"phone": "555-0100", "current_location": "Santa Cruz, CA", "country": "United States"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["country"] == "United States"
    assert body["current_location"] == "Santa Cruz, CA"
    assert body["phone"] == "555-0100"

    again = client.get("/api/candidate")
    assert again.json()["country"] == "United States"
    assert again.json()["current_location"] == "Santa Cruz, CA"

    cleared = client.patch("/api/candidate", json={"country": None})
    assert cleared.json()["country"] is None
    assert cleared.json()["current_location"] == "Santa Cruz, CA"


def test_preferences_requires_existing_candidate(client):
    resp = client.get("/api/candidate/preferences")
    assert resp.status_code == 404


def test_preferences_round_trip(client):
    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis3@example.com"})

    read_default = client.get("/api/candidate/preferences")
    assert read_default.status_code == 200
    assert read_default.json()["locations"] == []

    update_payload = {
        "remote_ok": True,
        "target_employment_types": ["internship", "new_grad"],
        "target_start_window_start": "2027-03-01",
        "target_start_window_end": "2027-09-01",
        "min_match_score_to_surface": 40,
        "locations": [
            {"label": "California", "location_type": "state", "priority": 0},
            {"label": "Seattle", "location_type": "metro", "priority": 1},
            {"label": "Remote", "location_type": "remote", "priority": 2},
        ],
        "roles": [
            {"role_category": "swe_backend", "priority": 0},
            {"role_category": "swe_fullstack", "priority": 1},
        ],
    }
    update_resp = client.put("/api/candidate/preferences", json=update_payload)
    assert update_resp.status_code == 200, update_resp.text
    body = update_resp.json()
    assert body["min_match_score_to_surface"] == 40
    assert [loc["label"] for loc in body["locations"]] == ["California", "Seattle", "Remote"]
    assert [role["role_category"] for role in body["roles"]] == ["swe_backend", "swe_fullstack"]

    # Re-reading shows the same persisted state (not just the response echo).
    reread = client.get("/api/candidate/preferences")
    assert reread.status_code == 200
    assert len(reread.json()["locations"]) == 3


def test_invalid_email_rejected_with_422(client):
    resp = client.post("/api/candidate", json={"full_name": "Bad Email", "email": "not-an-email"})
    assert resp.status_code == 422
