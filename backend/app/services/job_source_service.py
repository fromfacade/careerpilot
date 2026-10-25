"""Job source registry (module 2): employers + the board each is polled on."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.job_source import Employer, JobSource
from app.schemas.job_source import JobSourceCreate, JobSourceUpdate


def get_or_create_employer(db: Session, name: str) -> Employer:
    employer = db.execute(select(Employer).where(Employer.name == name)).scalar_one_or_none()
    if employer is not None:
        return employer
    employer = Employer(name=name)
    db.add(employer)
    db.flush()
    return employer


def list_job_sources(db: Session) -> list[JobSource]:
    return list(
        db.execute(select(JobSource).options(joinedload(JobSource.employer)).order_by(JobSource.id)).scalars()
    )


def get_job_source_or_404(db: Session, job_source_id: int) -> JobSource:
    job_source = db.execute(
        select(JobSource).options(joinedload(JobSource.employer)).where(JobSource.id == job_source_id)
    ).scalar_one_or_none()
    if job_source is None:
        raise NotFoundError(f"Job source {job_source_id} not found")
    return job_source


def create_job_source(db: Session, data: JobSourceCreate) -> JobSource:
    employer = get_or_create_employer(db, data.employer_name)
    job_source = JobSource(
        employer_id=employer.id,
        provider=data.provider,
        board_token=data.board_token,
        is_enabled=data.is_enabled,
        fetch_interval_minutes=data.fetch_interval_minutes,
    )
    db.add(job_source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Job source for provider={data.provider.value} board_token={data.board_token} already exists"
        ) from exc
    db.refresh(job_source)
    return job_source


def update_job_source(db: Session, job_source_id: int, data: JobSourceUpdate) -> JobSource:
    job_source = get_job_source_or_404(db, job_source_id)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(job_source, field, value)
    db.commit()
    db.refresh(job_source)
    return job_source
