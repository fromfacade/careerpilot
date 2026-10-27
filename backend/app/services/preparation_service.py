"""Job-specific application preparation.

Creates and updates review material for one job. This module never submits
an application or opens an employer form.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import (
    CanonicalFactStatus,
    FactVerificationStatus,
    OPEN_PREPARATION_STATES,
    PreparationState,
)
from app.models.job import Job
from app.models.job_source import JobSource
from app.models.preparation import ApplicationPreparation
from app.models.resume import Resume
from app.services import canonical_service, resume_service
from app.services.job_analysis import analyze_job_description, match_qualifications
from app.services.resume_export import export_docx, export_pdf
from app.services.resume_tailor import tailor_resume


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
    return analyze_preparation(db, candidate, row.id)


def cancel_preparation(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    if row.state is PreparationState.CANCELLED:
        return row
    row.state = PreparationState.CANCELLED
    db.commit()
    db.refresh(row)
    return row


def _verified_facts(db: Session, candidate: Candidate):
    return [
        fact
        for fact in canonical_service.list_canonical_facts(
            db, candidate, status=CanonicalFactStatus.ACTIVE
        )
        if fact.verification_status in {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}
        and not fact.needs_review
    ]


def analyze_preparation(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    job = db.get(Job, row.job_id) if row.job_id else None
    row.analysis = analyze_job_description(row.snapshot_description, job)
    facts = _verified_facts(db, candidate)
    row.match_report = match_qualifications(row.analysis, facts, candidate)
    if not row.snapshot_description.strip():
        return mark_failed(db, row, "This job has no description to analyze.")
    row.tailored_resume = tailor_resume(candidate, facts, row.analysis)
    _export_tailored_files(row)
    row.state = PreparationState.NEEDS_REVIEW
    row.error_message = ""
    db.commit()
    db.refresh(row)
    return row


def _export_tailored_files(row: ApplicationPreparation) -> None:
    settings = get_settings()
    folder = Path(settings.preparation_storage_dir) / str(row.id)
    try:
        row.docx_path = str(export_docx(row.tailored_resume, folder / "tailored.docx"))
        row.pdf_path = str(export_pdf(row.tailored_resume, folder / "tailored.pdf"))
    except Exception as exc:  # export must not erase analysis or invent facts
        row.error_message = f"Tailored resume files could not be generated: {exc}"


def update_tailored_resume(db: Session, candidate: Candidate, preparation_id: int, payload) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    if payload.tailored_resume is not None:
        allowed = set(row.tailored_resume.get("source_fact_ids") or [])
        incoming_ids = set(payload.tailored_resume.get("source_fact_ids") or allowed)
        if incoming_ids - allowed:
            raise ValidationError("A tailored resume cannot add facts that were not already verified.")
        row.tailored_resume = payload.tailored_resume
        _export_tailored_files(row)
    if payload.status is not None:
        row.tailored_resume_status = payload.status
    mark_ready_if_approved(db, row)
    return get_preparation_or_404(db, candidate, row.id)


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
