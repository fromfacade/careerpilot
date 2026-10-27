"""Job-specific application preparation.

Creates and updates review material for one job. This module never submits
an application or opens an employer form.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import OPEN_PREPARATION_STATES, PreparationState
from app.models.job import Job
from app.models.job_source import JobSource
from app.models.preparation import ApplicationPreparation
from app.models.resume import Resume
from app.services import resume_service


DESIGN_LIMITATION = (
    "The original resume's visual design is not reproduced. CareerPilot exports "
    "an ATS-friendly layout from verified facts. Download the original file to "
    "compare side by side."
)


def _load_job(db: Session, job_id: int) -> Job:
    job = db.execute(
        select(Job).options(joinedload(Job.job_source).joinedload(JobSource.employer)).where(Job.id == job_id)
    ).unique().scalar_one_or_none()
    if job is None:
        raise NotFoundError(f"No job with id={job_id}.")
    return job


def _primary_resume(db: Session, candidate: Candidate) -> Resume | None:
    return next((row for row in resume_service.list_resumes(db, candidate) if row.is_primary), None)


def get_open_preparation(db: Session, candidate: Candidate, job_id: int) -> ApplicationPreparation | None:
    return db.execute(
        select(ApplicationPreparation)
        .options(selectinload(ApplicationPreparation.answers))
        .where(
            ApplicationPreparation.candidate_id == candidate.id,
            ApplicationPreparation.job_id == job_id,
            ApplicationPreparation.state.in_(tuple(OPEN_PREPARATION_STATES)),
        )
    ).scalar_one_or_none()


def get_preparation_or_404(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = db.execute(
        select(ApplicationPreparation)
        .options(selectinload(ApplicationPreparation.answers))
        .where(
            ApplicationPreparation.id == preparation_id,
            ApplicationPreparation.candidate_id == candidate.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"No application preparation with id={preparation_id}.")
    return row


def list_preparations(db: Session, candidate: Candidate) -> list[ApplicationPreparation]:
    return list(
        db.execute(
            select(ApplicationPreparation)
            .options(selectinload(ApplicationPreparation.answers))
            .where(ApplicationPreparation.candidate_id == candidate.id)
            .order_by(ApplicationPreparation.id.desc())
        ).scalars().all()
    )


def create_or_get_preparation(db: Session, candidate: Candidate, job_id: int) -> ApplicationPreparation:
    existing = get_open_preparation(db, candidate, job_id)
    if existing is not None:
        return existing
    job = _load_job(db, job_id)
    if not (job.description_text or "").strip():
        raise ValidationError("This job has no description to prepare from.")
    employer = job.job_source.employer.name if job.job_source and job.job_source.employer else "Unknown employer"
    resume = _primary_resume(db, candidate)
    row = ApplicationPreparation(
        candidate_id=candidate.id,
        job_id=job.id,
        source_resume_id=resume.id if resume else None,
        state=PreparationState.PREPARING,
        snapshot_job_title=job.title,
        snapshot_employer=employer,
        snapshot_description=job.description_text,
        snapshot_apply_url=job.apply_url,
        snapshot_content_hash=job.content_hash,
        design_limitation=DESIGN_LIMITATION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return get_preparation_or_404(db, candidate, row.id)


def cancel_preparation(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    if row.state is PreparationState.CANCELLED:
        return row
    row.state = PreparationState.CANCELLED
    db.commit()
    db.refresh(row)
    return row


def mark_needs_review(db: Session, row: ApplicationPreparation) -> ApplicationPreparation:
    row.state = PreparationState.NEEDS_REVIEW
    row.error_message = ""
    db.commit()
    db.refresh(row)
    return row


def mark_failed(db: Session, row: ApplicationPreparation, message: str) -> ApplicationPreparation:
    row.state = PreparationState.FAILED
    row.error_message = message
    db.commit()
    db.refresh(row)
    return row


def mark_ready_if_approved(db: Session, row: ApplicationPreparation) -> ApplicationPreparation:
    answers = row.answers
    resume_ok = row.tailored_resume_status.value == "approved" if row.tailored_resume else False
    answers_ok = bool(answers) and all(item.status.value == "approved" for item in answers)
    if resume_ok and answers_ok:
        row.state = PreparationState.READY
    else:
        row.state = PreparationState.NEEDS_REVIEW
    db.commit()
    db.refresh(row)
    return row
