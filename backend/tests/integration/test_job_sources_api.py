from __future__ import annotations


def test_list_job_sources_empty_initially(client):
    resp = client.get("/api/job-sources")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_job_source_creates_employer_too(client):
    payload = {
        "employer_name": "Acme Corp",
        "provider": "greenhouse",
        "board_token": "acme",
        "is_enabled": True,
        "fetch_interval_minutes": 180,
    }
    resp = client.post("/api/job-sources", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["employer_name"] == "Acme Corp"
    assert body["provider"] == "greenhouse"
    assert body["board_token"] == "acme"
    assert body["last_fetch_status"] == "never_run"

    listed = client.get("/api/job-sources").json()
    assert len(listed) == 1


def test_duplicate_provider_board_token_returns_409(client):
    payload = {"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme"}
    first = client.post("/api/job-sources", json=payload)
    assert first.status_code == 201

    second = client.post(
        "/api/job-sources", json={"employer_name": "Different Name Inc", "provider": "greenhouse", "board_token": "acme"}
    )
    assert second.status_code == 409


def test_reusing_employer_name_attaches_to_same_employer(client):
    client.post("/api/job-sources", json={"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme-gh"})
    resp = client.post("/api/job-sources", json={"employer_name": "Acme Corp", "provider": "lever", "board_token": "acme-lever"})
    assert resp.status_code == 201

    sources = client.get("/api/job-sources").json()
    employer_ids = {s["employer_id"] for s in sources}
    assert len(employer_ids) == 1  # same employer reused across both sources


def test_update_job_source_disable(client):
    create_resp = client.post("/api/job-sources", json={"employer_name": "Acme Corp", "provider": "ashby", "board_token": "acme"})
    job_source_id = create_resp.json()["id"]

    update_resp = client.patch(f"/api/job-sources/{job_source_id}", json={"is_enabled": False})
    assert update_resp.status_code == 200
    assert update_resp.json()["is_enabled"] is False


def test_update_nonexistent_job_source_returns_404(client):
    resp = client.patch("/api/job-sources/999999", json={"is_enabled": False})
    assert resp.status_code == 404


def test_invalid_provider_rejected_with_422(client):
    resp = client.post(
        "/api/job-sources", json={"employer_name": "Acme Corp", "provider": "not-a-real-provider", "board_token": "acme"}
    )
    assert resp.status_code == 422
