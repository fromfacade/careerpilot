from __future__ import annotations

import json
from pathlib import Path

from app.models.enums import JobProvider
from app.models.job_source import Employer, JobSource

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())


class _FakeResponse:
    def __init__(self, json_data):
        self.status_code = 200
        self._json_data = json_data
        self.request = None

    def json(self):
        return self._json_data


def test_trigger_discovery_with_no_sources_succeeds_trivially(client):
    resp = client.post("/api/discovery/runs")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["sources_attempted"] == 0


def test_trigger_discovery_persists_jobs_and_reports_per_source_detail(client, db_session, monkeypatch):
    employer = Employer(name="Acme Corp")
    db_session.add(employer)
    db_session.flush()
    db_session.add(JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token="acme-gh", is_enabled=True))
    db_session.commit()

    fixture = _load_fixture("greenhouse_jobs.json")
    monkeypatch.setattr(
        "app.sources.http.httpx.get", lambda url, params=None, timeout=None: _FakeResponse(fixture)
    )

    resp = client.post("/api/discovery/runs")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["jobs_created"] == 3
    assert len(body["sources"]) == 1
    assert body["sources"][0]["employer_name"] == "Acme Corp"
    assert body["sources"][0]["status"] == "success"
    assert body["sources"][0]["jobs_found"] == 3

    jobs_resp = client.get("/api/jobs")
    assert len(jobs_resp.json()) == 3


def test_list_runs_and_latest_run(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.sources.http.httpx.get", lambda url, params=None, timeout=None: _FakeResponse({"jobs": []})
    )

    first = client.post("/api/discovery/runs").json()
    second = client.post("/api/discovery/runs").json()

    runs = client.get("/api/discovery/runs").json()
    assert len(runs) == 2
    assert runs[0]["id"] == second["id"]  # most recent first

    latest = client.get("/api/discovery/runs/latest").json()
    assert latest["id"] == second["id"]


def test_latest_run_is_null_when_no_runs_yet(client):
    resp = client.get("/api/discovery/runs/latest")
    assert resp.status_code == 200
    assert resp.json() is None
