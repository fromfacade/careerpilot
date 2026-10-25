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


# --- Priority 1/2: sorting, filtering, pagination, views ------------------
#
# Fixture `greenhouse_jobs.json` gives three jobs with known, distinct
# titles/locations/dates, which lets these tests assert *exact* orderings
# and filter results rather than just "some subset changed":
#   1001 "Software Engineer, Backend Infrastructure" | San Francisco, CA | posted 2026-10-01 -> swe_backend, unknown employment type
#   1002 "Software Engineering Intern - Summer 2027"  | Remote - US      | posted 2026-10-05 -> swe_backend, internship, remote
#   1003 "IT Support Specialist"                       | Seattle, WA      | posted 2026-09-20 -> it_support, unknown employment type


def _discover_one_company(client, monkeypatch, employer_name="Acme Corp", provider="greenhouse", token="acme"):
    def _fake(url, params=None, timeout=None):
        return _FakeResponse(200, _load_fixture("greenhouse_jobs.json"))

    monkeypatch.setattr("app.sources.http.httpx.get", _fake)
    client.post(
        "/api/job-sources",
        json={"employer_name": employer_name, "provider": provider, "board_token": token},
    )
    run = client.post("/api/discovery/runs").json()
    assert run["jobs_created"] == 3, run


def test_sort_newest_and_oldest_first_use_entire_result_set_not_just_current_page(client, monkeypatch):
    _discover_one_company(client, monkeypatch)

    newest = client.get("/api/jobs", params={"sort": "newest_first"})
    assert [j["title"] for j in newest.json()] == [
        "Software Engineering Intern - Summer 2027",
        "Software Engineer, Backend Infrastructure",
        "IT Support Specialist",
    ]
    assert newest.headers["X-Total-Count"] == "3"

    oldest = client.get("/api/jobs", params={"sort": "oldest_first"})
    assert [j["title"] for j in oldest.json()] == [
        "IT Support Specialist",
        "Software Engineer, Backend Infrastructure",
        "Software Engineering Intern - Summer 2027",
    ]

    # Paginating one-at-a-time must walk the *same* global order as above,
    # proving sorting is applied to the whole result set before pagination
    # (not just within whatever page happened to load) -- this was a real
    # bug in the original implementation (filtered/paginated in the wrong
    # order relative to each other).
    page0 = client.get("/api/jobs", params={"sort": "newest_first", "limit": 1, "offset": 0})
    page1 = client.get("/api/jobs", params={"sort": "newest_first", "limit": 1, "offset": 1})
    page2 = client.get("/api/jobs", params={"sort": "newest_first", "limit": 1, "offset": 2})
    assert page0.headers["X-Total-Count"] == "3"
    assert [page0.json()[0]["title"], page1.json()[0]["title"], page2.json()[0]["title"]] == [
        "Software Engineering Intern - Summer 2027",
        "Software Engineer, Backend Infrastructure",
        "IT Support Specialist",
    ]


def test_sort_company_name_asc_and_desc(client, monkeypatch):
    _discover_one_company(client, monkeypatch, employer_name="Acme Corp", provider="greenhouse", token="acme")
    _discover_one_company(client, monkeypatch, employer_name="Beta Corp", provider="greenhouse", token="beta")

    asc = client.get("/api/jobs", params={"sort": "company_asc"}).json()
    assert asc[0]["employer_name"] == "Acme Corp"
    assert asc[-1]["employer_name"] == "Beta Corp"

    desc = client.get("/api/jobs", params={"sort": "company_desc"}).json()
    assert desc[0]["employer_name"] == "Beta Corp"
    assert desc[-1]["employer_name"] == "Acme Corp"


def test_filter_by_role_category_employment_type_and_remote_type(client, monkeypatch):
    _discover_one_company(client, monkeypatch)

    backend_only = client.get("/api/jobs", params={"role_categories": "swe_backend"}).json()
    assert {j["title"] for j in backend_only} == {
        "Software Engineer, Backend Infrastructure",
        "Software Engineering Intern - Summer 2027",
    }

    internship_only = client.get("/api/jobs", params={"employment_types": "internship"}).json()
    assert [j["title"] for j in internship_only] == ["Software Engineering Intern - Summer 2027"]

    remote_only = client.get("/api/jobs", params={"remote_types": "remote"}).json()
    assert [j["title"] for j in remote_only] == ["Software Engineering Intern - Summer 2027"]

    it_support_only = client.get("/api/jobs", params={"role_categories": "it_support"}).json()
    assert [j["title"] for j in it_support_only] == ["IT Support Specialist"]


def test_filter_by_location_text_and_posted_within_days(client, monkeypatch):
    _discover_one_company(client, monkeypatch)

    seattle = client.get("/api/jobs", params={"location": "seattle"}).json()
    assert [j["title"] for j in seattle] == ["IT Support Specialist"]

    # Generous 30-day margin (instead of a tight boundary) so this isn't
    # flaky relative to time-of-day: jobs 1001 (Oct 1) and 1002 (Oct 5) both
    # fall well within the window, while 1003 (Sep 20) falls well outside it.
    recent = client.get("/api/jobs", params={"posted_within_days": 30}).json()
    assert {j["title"] for j in recent} == {
        "Software Engineer, Backend Infrastructure",
        "Software Engineering Intern - Summer 2027",
    }


def test_filtering_never_deletes_jobs_from_the_database(client, monkeypatch):
    _discover_one_company(client, monkeypatch)

    # A filter that matches nothing...
    empty = client.get("/api/jobs", params={"role_categories": "qa"})
    assert empty.json() == []
    assert empty.headers["X-Total-Count"] == "0"

    # ...must never remove the underlying rows. All 3 jobs are still there.
    everything = client.get("/api/jobs")
    assert len(everything.json()) == 3
    assert everything.headers["X-Total-Count"] == "3"


def test_recommended_view_enforces_min_match_score_and_all_view_does_not(client, monkeypatch):
    """Direct regression coverage for Priority 3 at the API layer: the
    candidate's `min_match_score_to_surface` preference must actually be
    enforced by the Recommended view (previously it was never enforced
    anywhere), while the All Jobs view must keep showing everything --
    filtering must never hide the existence of jobs from the user
    entirely, only from the curated/default view.
    """
    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis4@example.com"})
    client.put(
        "/api/candidate/preferences",
        json={"min_match_score_to_surface": 100},
    )
    _discover_one_company(client, monkeypatch)

    recommended = client.get("/api/jobs", params={"view": "recommended"})
    assert recommended.json() == []

    all_jobs = client.get("/api/jobs", params={"view": "all"})
    assert len(all_jobs.json()) == 3

    # Also true for the bare default (no `view` at all), preserving the
    # pre-existing "GET /api/jobs with no params returns everything"
    # contract older callers (and the dashboard before this feature) rely
    # on.
    default = client.get("/api/jobs")
    assert len(default.json()) == 3


def test_recommended_view_excludes_dismissed_by_default_but_all_view_shows_it(client, monkeypatch):
    client.post("/api/candidate", json={"full_name": "Luis", "email": "luis5@example.com"})
    _discover_one_company(client, monkeypatch)

    jobs = client.get("/api/jobs").json()
    job_id = jobs[0]["id"]
    client.patch(f"/api/jobs/{job_id}/state", json={"state": "dismissed"})

    recommended = client.get("/api/jobs", params={"view": "recommended"}).json()
    assert all(j["id"] != job_id for j in recommended)

    all_jobs = client.get("/api/jobs", params={"view": "all"}).json()
    assert any(j["id"] == job_id for j in all_jobs)

    dismissed_explicit = client.get("/api/jobs", params={"states": "dismissed"}).json()
    assert any(j["id"] == job_id for j in dismissed_explicit)
