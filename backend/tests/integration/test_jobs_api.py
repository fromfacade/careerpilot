"""Integration tests for job source registry + jobs + save/dismiss state
APIs, against the real careerpilot_test database."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())


class _FakeResponse:
    def __init__(self, status_code: int, json_data):
        self.status_code = status_code
        self._json_data = json_data
        self.request = None

    def json(self):
        return self._json_data


def test_create_and_list_job_sources(client):
    resp = client.post(
        "/api/job-sources",
        json={"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["employer_name"] == "Acme Corp"
    assert body["last_fetch_status"] == "never_run"

    listing = client.get("/api/job-sources")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_duplicate_job_source_returns_409(client):
    payload = {"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme"}
    assert client.post("/api/job-sources", json=payload).status_code == 201
    assert client.post("/api/job-sources", json=payload).status_code == 409


def test_disable_job_source(client):
    created = client.post(
        "/api/job-sources",
        json={"employer_name": "Acme Corp", "provider": "lever", "board_token": "acme-lever"},
    ).json()

    resp = client.patch(f"/api/job-sources/{created['id']}", json={"is_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False


def test_jobs_list_empty_initially(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_discovery_then_jobs_list_shows_real_persisted_jobs(client, monkeypatch):
    def _fake(url, params=None, timeout=None):
        return _FakeResponse(200, _load_fixture("greenhouse_jobs.json"))

    monkeypatch.setattr("app.sources.http.httpx.get", _fake)

    client.post(
        "/api/job-sources",
        json={"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme"},
    )

    run_resp = client.post("/api/discovery/runs")
    assert run_resp.status_code == 201, run_resp.text
    assert run_resp.json()["status"] == "succeeded"
    assert run_resp.json()["jobs_created"] == 3

    jobs_resp = client.get("/api/jobs")
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert len(jobs) == 3
    assert all(job["state"] == "new" for job in jobs)
    assert all(job["employer_name"] == "Acme Corp" for job in jobs)
    assert all(job["assessment"] is None for job in jobs)  # no candidate profile yet


def test_save_and_dismiss_job_state(client, monkeypatch):
    def _fake(url, params=None, timeout=None):
        return _FakeResponse(200, _load_fixture("greenhouse_jobs.json"))

    monkeypatch.setattr("app.sources.http.httpx.get", _fake)

    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis@example.com"})
    client.post(
        "/api/job-sources",
        json={"employer_name": "Acme Corp", "provider": "greenhouse", "board_token": "acme"},
    )
    run = client.post("/api/discovery/runs").json()
    assert run["jobs_created"] == 3

    jobs = client.get("/api/jobs").json()
    job_id = jobs[0]["id"]

    # With a candidate profile present, assessments should now be populated.
    assert jobs[0]["assessment"] is not None
    assert jobs[0]["assessment"]["eligibility"] in {"eligible", "ineligible", "unknown"}

    save_resp = client.patch(f"/api/jobs/{job_id}/state", json={"state": "saved"})
    assert save_resp.status_code == 200
    assert save_resp.json()["state"] == "saved"

    saved_list = client.get("/api/jobs", params={"state": "saved"}).json()
    assert len(saved_list) == 1
    assert saved_list[0]["id"] == job_id

    dismiss_resp = client.patch(f"/api/jobs/{job_id}/state", json={"state": "dismissed", "state_reason": "Not interested"})
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["state"] == "dismissed"

    new_list = client.get("/api/jobs", params={"state": "new"}).json()
    assert all(job["id"] != job_id for job in new_list)


def test_unknown_job_state_update_returns_404(client):
    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis@example.com"})
    resp = client.patch("/api/jobs/999999/state", json={"state": "saved"})
    assert resp.status_code == 404
