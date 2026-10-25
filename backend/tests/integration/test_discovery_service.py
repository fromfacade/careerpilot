"""End-to-end discovery tests against the real careerpilot_test PostgreSQL
database. HTTP is stubbed at the `httpx.get` boundary (same technique as
tests/unit/test_adapters.py) with fixture payloads, so this proves the full
path — HTTP response -> adapter parsing -> normalization -> dedup ->
persistence -> DiscoveryRun bookkeeping — actually writes correct rows to
Postgres, not just that functions return without erroring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.exceptions import JobSourceFetchError
from app.models.discovery import DiscoveryRun
from app.models.enums import FetchStatus, JobProvider, RunStatus, TriggerType
from app.models.job import Job
from app.models.job_source import Employer, JobSource
from app.services import discovery_service

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


def _install_fake_get(monkeypatch, payload_by_board: dict[str, object], *, fail_boards: set[str] | None = None):
    fail_boards = fail_boards or set()

    def _fake(url, params=None, timeout=None):
        for board, payload in payload_by_board.items():
            if board in url:
                if board in fail_boards:
                    import httpx

                    raise httpx.ConnectTimeout("simulated timeout")
                return _FakeResponse(200, payload)
        raise AssertionError(f"Unexpected URL in test: {url}")

    monkeypatch.setattr("app.sources.http.httpx.get", _fake)


def _make_job_source(db, *, employer_name: str, provider: JobProvider, board_token: str) -> JobSource:
    employer = db.execute(select(Employer).where(Employer.name == employer_name)).scalar_one_or_none()
    if employer is None:
        employer = Employer(name=employer_name)
        db.add(employer)
        db.flush()
    job_source = JobSource(employer_id=employer.id, provider=provider, board_token=board_token, is_enabled=True)
    db.add(job_source)
    db.commit()
    db.refresh(job_source)
    return job_source


class TestDiscoveryServiceEndToEnd:
    def test_first_run_persists_jobs_to_postgres(self, db_session, monkeypatch):
        job_source = _make_job_source(
            db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh"
        )
        _install_fake_get(monkeypatch, {"acme-gh": _load_fixture("greenhouse_jobs.json")})

        run = discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        assert run.status == RunStatus.SUCCEEDED
        assert run.sources_attempted == 1
        assert run.sources_succeeded == 1
        assert run.jobs_created == 3
        assert run.jobs_updated == 0

        persisted = db_session.execute(select(Job).where(Job.job_source_id == job_source.id)).scalars().all()
        assert len(persisted) == 3
        titles = {j.title for j in persisted}
        assert "Software Engineer, Backend Infrastructure" in titles
        intern_job = next(j for j in persisted if "Intern" in j.title)
        assert intern_job.employment_type.value == "internship"
        assert intern_job.is_active is True
        assert intern_job.raw_payload["id"] == 1002

        db_session.refresh(job_source)
        assert job_source.last_fetch_status == FetchStatus.SUCCESS
        assert job_source.last_fetched_at is not None

    def test_second_run_updates_without_duplicating(self, db_session, monkeypatch):
        _make_job_source(db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh")
        _install_fake_get(monkeypatch, {"acme-gh": _load_fixture("greenhouse_jobs.json")})

        discovery_service.run_discovery(db_session, TriggerType.MANUAL)
        second_run = discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        assert second_run.jobs_created == 0
        assert second_run.jobs_updated == 3

        all_jobs = db_session.execute(select(Job)).scalars().all()
        assert len(all_jobs) == 3  # still exactly 3, not 6

    def test_removed_job_is_deactivated_not_deleted(self, db_session, monkeypatch):
        _make_job_source(db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh")
        full_fixture = _load_fixture("greenhouse_jobs.json")
        _install_fake_get(monkeypatch, {"acme-gh": full_fixture})
        discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        reduced_fixture = {"jobs": full_fixture["jobs"][:2]}  # drop the 3rd job
        _install_fake_get(monkeypatch, {"acme-gh": reduced_fixture})
        second_run = discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        assert second_run.jobs_deactivated == 1
        all_jobs = db_session.execute(select(Job)).scalars().all()
        assert len(all_jobs) == 3  # row still exists
        inactive = [j for j in all_jobs if not j.is_active]
        assert len(inactive) == 1
        assert inactive[0].external_id == "1003"

    def test_source_failure_is_isolated_and_run_is_partial(self, db_session, monkeypatch):
        good_source = _make_job_source(
            db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh"
        )
        bad_source = _make_job_source(
            db_session, employer_name="Broken Co", provider=JobProvider.GREENHOUSE, board_token="broken-gh"
        )
        _install_fake_get(
            monkeypatch,
            {"acme-gh": _load_fixture("greenhouse_jobs.json"), "broken-gh": {}},
            fail_boards={"broken-gh"},
        )

        run = discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        assert run.status == RunStatus.PARTIAL
        assert run.sources_attempted == 2
        assert run.sources_succeeded == 1

        db_session.refresh(bad_source)
        assert bad_source.last_fetch_status == FetchStatus.FAILURE
        assert bad_source.last_fetch_error is not None

        db_session.refresh(good_source)
        assert good_source.last_fetch_status == FetchStatus.SUCCESS

        # The good source's jobs were still persisted despite the other source failing.
        good_jobs = db_session.execute(select(Job).where(Job.job_source_id == good_source.id)).scalars().all()
        assert len(good_jobs) == 3

    def test_all_sources_failing_marks_run_failed(self, db_session, monkeypatch):
        _make_job_source(db_session, employer_name="Broken Co", provider=JobProvider.GREENHOUSE, board_token="broken-gh")
        _install_fake_get(monkeypatch, {"broken-gh": {}}, fail_boards={"broken-gh"})

        run = discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        assert run.status == RunStatus.FAILED
        assert run.error_summary is not None

    def test_cross_source_duplicate_is_flagged(self, db_session, monkeypatch):
        # Same employer, same title/location fixture served from two different
        # "boards" (simulating a cross-posted listing) should be flagged as a
        # duplicate of the first, not shown as a second distinct job.
        _make_job_source(db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh-1")
        _make_job_source(db_session, employer_name="Acme Corp", provider=JobProvider.GREENHOUSE, board_token="acme-gh-2")
        fixture = _load_fixture("greenhouse_jobs.json")
        _install_fake_get(monkeypatch, {"acme-gh-1": fixture, "acme-gh-2": fixture})

        discovery_service.run_discovery(db_session, TriggerType.MANUAL)

        all_jobs = db_session.execute(select(Job)).scalars().all()
        assert len(all_jobs) == 6  # 3 per source, all stored

        duplicates = [j for j in all_jobs if j.duplicate_of_job_id is not None]
        assert len(duplicates) == 3  # the second source's 3 jobs are flagged as duplicates

    def test_discovery_run_rejected_while_one_is_in_progress(self, db_session, monkeypatch):
        from app.core.exceptions import ConflictError

        db_session.add(DiscoveryRun(trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING))
        db_session.commit()

        with pytest.raises(ConflictError):
            discovery_service.run_discovery(db_session, TriggerType.MANUAL)
