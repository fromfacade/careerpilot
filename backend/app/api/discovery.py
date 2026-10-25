from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import ConflictError
from app.models.enums import TriggerType
from app.schemas.discovery import DiscoveryRunRead, DiscoveryRunSourceRead
from app.scheduling.scheduler import is_scheduler_running
from app.services import candidate_service, discovery_service, job_service

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.get("/scheduler-status")
def scheduler_status():
    settings = get_settings()
    return {
        "enabled": settings.discovery_scheduler_enabled,
        "interval_minutes": settings.discovery_interval_minutes,
        "running": is_scheduler_running(),
    }


def _to_read(run) -> DiscoveryRunRead:
    sources = [
        DiscoveryRunSourceRead(
            job_source_id=s.job_source_id,
            provider=s.job_source.provider.value,
            board_token=s.job_source.board_token,
            employer_name=s.job_source.employer.name,
            status=s.status,
            jobs_found=s.jobs_found,
            jobs_created=s.jobs_created,
            jobs_updated=s.jobs_updated,
            error_message=s.error_message,
            started_at=s.started_at,
            finished_at=s.finished_at,
        )
        for s in run.sources
    ]
    return DiscoveryRunRead(
        id=run.id,
        trigger_type=run.trigger_type,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        sources_attempted=run.sources_attempted,
        sources_succeeded=run.sources_succeeded,
        jobs_created=run.jobs_created,
        jobs_updated=run.jobs_updated,
        jobs_deactivated=run.jobs_deactivated,
        error_summary=run.error_summary,
        sources=sources,
    )


@router.post("/runs", response_model=DiscoveryRunRead, status_code=201)
def trigger_discovery_run(db: Session = Depends(get_db)):
    try:
        run = discovery_service.run_discovery(db, TriggerType.MANUAL)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    candidate = candidate_service.get_candidate(db)
    if candidate is not None:
        job_service.recompute_all_assessments(db, candidate)

    return _to_read(run)


@router.get("/runs", response_model=list[DiscoveryRunRead])
def list_runs(limit: int = 10, db: Session = Depends(get_db)):
    runs = discovery_service.list_discovery_runs(db, limit=limit)
    return [_to_read(r) for r in runs]


@router.get("/runs/latest", response_model=DiscoveryRunRead | None)
def latest_run(db: Session = Depends(get_db)):
    run = discovery_service.get_latest_discovery_run(db)
    return _to_read(run) if run else None
