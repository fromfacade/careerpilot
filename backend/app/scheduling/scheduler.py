"""Basic periodic discovery scheduling (module 12, scheduling half).

Uses APScheduler's BackgroundScheduler to call the exact same
`discovery_service.run_discovery` entry point the manual "Run discovery" API
endpoint uses — there is only one discovery code path, scheduled or manual.

This is deliberately simple for Phase 1: a single interval job, configured
via `DISCOVERY_INTERVAL_MINUTES`/`DISCOVERY_SCHEDULER_ENABLED`. It does not
attempt per-source scheduling (each job_source also has its own
`fetch_interval_minutes` column reserved for a future, more granular
scheduler — see docs/data-model.md).
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.exceptions import ConflictError
from app.core.logging import get_logger, log_extra
from app.models.enums import TriggerType
from app.services import candidate_service, discovery_service, job_service

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scheduled_discovery_job() -> None:
    with session_scope() as db:
        try:
            run = discovery_service.run_discovery(db, TriggerType.SCHEDULED)
        except ConflictError:
            logger.info("scheduled_discovery_skipped_already_running")
            return

        candidate = candidate_service.get_candidate(db)
        if candidate is not None:
            job_service.recompute_all_assessments(db, candidate)

        logger.info(
            "scheduled_discovery_finished",
            extra=log_extra(run_id=run.id, status=run.status.value, jobs_created=run.jobs_created),
        )


def start_scheduler() -> BackgroundScheduler | None:
    """Starts the background scheduler if enabled in settings. Safe to call
    once at app startup; returns None (and logs) if disabled."""
    global _scheduler
    settings = get_settings()

    if not settings.discovery_scheduler_enabled:
        logger.info("discovery_scheduler_disabled")
        return None

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_discovery_job,
        trigger="interval",
        minutes=settings.discovery_interval_minutes,
        id="discovery_run",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "discovery_scheduler_started",
        extra=log_extra(interval_minutes=settings.discovery_interval_minutes),
    )
    return scheduler


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("discovery_scheduler_stopped")
    _scheduler = None
