"""Unit tests for job source adapters.

No real network calls here — each test monkeypatches `httpx.get` (as used
by app.sources.http.get_json) to return a recorded fixture payload, so the
suite stays deterministic and fast. The adapters were validated against the
real Greenhouse/Lever/Ashby public APIs manually during development (see
docs/implementation-plan.md); this suite guards against regressions without
depending on those services being reachable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.enums import EmploymentType, RemoteType, RoleCategory
from app.sources import ashby, greenhouse, lever

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


@pytest.fixture()
def fake_get(monkeypatch):
    calls = []

    def _install(payload, status_code: int = 200):
        def _fake(url, params=None, timeout=None):
            calls.append({"url": url, "params": params})
            return _FakeResponse(status_code, payload)

        monkeypatch.setattr("app.sources.http.httpx.get", _fake)
        return calls

    return _install


class TestGreenhouseAdapter:
    def test_parses_jobs(self, fake_get):
        fake_get(_load_fixture("greenhouse_jobs.json"))
        jobs = greenhouse.fetch_jobs("acme")

        assert len(jobs) == 3
        first = jobs[0]
        assert first.external_id == "1001"
        assert first.title == "Software Engineer, Backend Infrastructure"
        assert first.locations == ["San Francisco, CA"]  # not split: see comment in greenhouse.py
        assert "backend infrastructure" in (first.description_html or "").lower()
        assert first.apply_url.startswith("https://boards.greenhouse.io")

    def test_multi_word_title_role_inference_input_available(self, fake_get):
        fake_get(_load_fixture("greenhouse_jobs.json"))
        jobs = greenhouse.fetch_jobs("acme")
        intern_job = next(j for j in jobs if "Intern" in j.title)
        assert intern_job.locations == ["Remote - US"]

    def test_raises_on_malformed_response(self, fake_get):
        fake_get({"not_jobs": []})
        from app.core.exceptions import JobSourceFetchError

        with pytest.raises(JobSourceFetchError):
            greenhouse.fetch_jobs("acme")


class TestLeverAdapter:
    def test_parses_jobs(self, fake_get):
        fake_get(_load_fixture("lever_jobs.json"))
        jobs = lever.fetch_jobs("acme")

        assert len(jobs) == 2
        full_stack = jobs[0]
        assert full_stack.title == "Full Stack Engineer"
        assert full_stack.remote_hint == "hybrid"
        assert full_stack.employment_type_hint == "Full-time"
        assert full_stack.description_plain == "Build and ship full stack features end to end."

        security = jobs[1]
        assert "not able to sponsor" in security.description_plain.lower()
        assert security.remote_hint == "remote"


class TestAshbyAdapter:
    def test_parses_listed_jobs_only(self, fake_get):
        fake_get(_load_fixture("ashby_jobs.json"))
        jobs = ashby.fetch_jobs("acme")

        # The 3rd fixture job has isListed=False and must be excluded.
        assert len(jobs) == 2
        titles = {j.title for j in jobs}
        assert titles == {"New Grad Software Engineer", "QA Engineer"}

    def test_employment_type_and_location_hints(self, fake_get):
        fake_get(_load_fixture("ashby_jobs.json"))
        jobs = ashby.fetch_jobs("acme")
        new_grad = next(j for j in jobs if "New Grad" in j.title)
        assert new_grad.employment_type_hint == "FullTime"
        assert new_grad.remote_hint == "Onsite"
        assert new_grad.locations == ["Seattle, Washington"]
