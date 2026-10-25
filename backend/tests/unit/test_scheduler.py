from __future__ import annotations

from app.scheduling import scheduler as scheduler_module


def test_scheduler_disabled_by_default_in_tests():
    # tests/conftest.py forces DISCOVERY_SCHEDULER_ENABLED=false before any
    # app module is imported, specifically so periodic jobs never run
    # against the real engine during a test session.
    result = scheduler_module.start_scheduler()
    assert result is None
    assert scheduler_module.is_scheduler_running() is False


def test_start_and_stop_scheduler_when_enabled(monkeypatch):
    from app.core import config

    settings = config.Settings(discovery_scheduler_enabled=True, discovery_interval_minutes=60)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)

    try:
        result = scheduler_module.start_scheduler()
        assert result is not None
        assert scheduler_module.is_scheduler_running() is True

        job_ids = {job.id for job in result.get_jobs()}
        assert "discovery_run" in job_ids
    finally:
        scheduler_module.stop_scheduler()
        assert scheduler_module.is_scheduler_running() is False
