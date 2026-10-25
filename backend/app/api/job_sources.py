from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.job_source import JobSourceCreate, JobSourceRead, JobSourceUpdate
from app.services import job_source_service

router = APIRouter(prefix="/api/job-sources", tags=["job-sources"])


def _to_read(job_source) -> JobSourceRead:
    return JobSourceRead(
        id=job_source.id,
        employer_id=job_source.employer_id,
        employer_name=job_source.employer.name,
        provider=job_source.provider,
        board_token=job_source.board_token,
        is_enabled=job_source.is_enabled,
        fetch_interval_minutes=job_source.fetch_interval_minutes,
        last_fetched_at=job_source.last_fetched_at,
        last_fetch_status=job_source.last_fetch_status,
        last_fetch_error=job_source.last_fetch_error,
        created_at=job_source.created_at,
        updated_at=job_source.updated_at,
    )


@router.get("", response_model=list[JobSourceRead])
def list_job_sources(db: Session = Depends(get_db)):
    return [_to_read(js) for js in job_source_service.list_job_sources(db)]


@router.post("", response_model=JobSourceRead, status_code=201)
def create_job_source(payload: JobSourceCreate, db: Session = Depends(get_db)):
    try:
        job_source = job_source_service.create_job_source(db, payload)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_read(job_source)


@router.patch("/{job_source_id}", response_model=JobSourceRead)
def update_job_source(job_source_id: int, payload: JobSourceUpdate, db: Session = Depends(get_db)):
    try:
        job_source = job_source_service.update_job_source(db, job_source_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_read(job_source)
