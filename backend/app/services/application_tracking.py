"""Create and update tracked applications.

Records hold job identity, status, and a short failure or confirmation note.
They do not hold answers, credentials, or contact details. Readiness can
move a record between preparing, needs_review, and ready_to_submit.
It cannot mark a record submitted.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import TrackedApplication
from app.models.enums import ApplicationStatus
from app.models.job import Job
from app.models.preparation import ApplicationPreparation

_EMAIL = re.compile(r"\S+@\S+")
_LONG_NUMBER = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_NOTE_STATUSES = {
    ApplicationStatus.NEEDS_REVIEW,
    ApplicationStatus.SUBMISSION_FAILED,
    ApplicationStatus.CONFIRMATION_UNKNOWN,
}
_CONFIRMATION_STATUSES = {
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.CONFIRMATION_UNKNOWN,
}
_READINESS_STATUSES = {ApplicationStatus.NEEDS_REVIEW, ApplicationStatus.READY_TO_SUBMIT}
_LOCKED = {
    ApplicationStatus.SUBMITTING,
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.CONFIRMATION_UNKNOWN,
}

ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.PREPARING: frozenset({ApplicationStatus.NEEDS_REVIEW, ApplicationStatus.READY_TO_SUBMIT}),
    ApplicationStatus.NEEDS_REVIEW: frozenset({ApplicationStatus.PREPARING, ApplicationStatus.READY_TO_SUBMIT}),
    ApplicationStatus.READY_TO_SUBMIT: frozenset(
        {ApplicationStatus.NEEDS_REVIEW, ApplicationStatus.PREPARING, ApplicationStatus.SUBMITTING}
    ),
    ApplicationStatus.SUBMITTING: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMISSION_FAILED, ApplicationStatus.CONFIRMATION_UNKNOWN}
    ),
    ApplicationStatus.SUBMITTED: frozenset(),
    ApplicationStatus.SUBMISSION_FAILED: frozenset(
        {ApplicationStatus.PREPARING, ApplicationStatus.NEEDS_REVIEW, ApplicationStatus.READY_TO_SUBMIT}
    ),
    ApplicationStatus.CONFIRMATION_UNKNOWN: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMISSION_FAILED}
    ),
}


def list_applications(db: Session, candidate_id: int) -> list[TrackedApplication]:
    return list(
        db.execute(
            select(TrackedApplication)
            .where(TrackedApplication.candidate_id == candidate_id)
            .order_by(TrackedApplication.id.desc())
        ).scalars().all()
    )


def get_application_or_404(db: Session, candidate_id: int, application_id: int) -> TrackedApplication:
    row = db.execute(
        select(TrackedApplication).where(
            TrackedApplication.id == application_id,
            TrackedApplication.candidate_id == candidate_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"No tracked application with id={application_id}.")
    return row


def find_for_preparation(db: Session, preparation: ApplicationPreparation) -> TrackedApplication | None:
    if preparation.job_id is None:
        return None
    return _find(db, preparation.candidate_id, preparation.job_id)


def ensure_for_preparation(db: Session, preparation: ApplicationPreparation) -> TrackedApplication:
    """Return the one application row for this job, creating it as preparing when needed."""
    if preparation.job_id is None:
        raise NotFoundError("This preparation is not linked to a job.")
    job = db.get(Job, preparation.job_id)
    if job is None:
        raise NotFoundError(f"No job with id={preparation.job_id}.")
    existing = _find(db, preparation.candidate_id, preparation.job_id)
    if existing is not None:
        if existing.preparation_id != preparation.id:
            existing.preparation_id = preparation.id
        if existing.resume_id != preparation.source_resume_id:
            existing.resume_id = preparation.source_resume_id
        if preparation.snapshot_employer and existing.employer != preparation.snapshot_employer:
            existing.employer = preparation.snapshot_employer
        if db.is_modified(existing):
            db.commit()
            db.refresh(existing)
        return existing
    employer = preparation.snapshot_employer or _employer_name(job)
    row = TrackedApplication(
        candidate_id=preparation.candidate_id,
        job_id=job.id,
        employer=employer,
        preparation_id=preparation.id,
        resume_id=preparation.source_resume_id,
        status=ApplicationStatus.PREPARING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_readiness(db: Session, *, candidate_id: int, preparation_id: int, readiness) -> TrackedApplication:
    """Copy a readiness verdict onto the tracked application. Never sets submitting or submitted."""
    try:
        status = ApplicationStatus(readiness.status)
    except ValueError as exc:
        raise ValidationError("A readiness result cannot mark an application submitted.") from exc
    if status not in _READINESS_STATUSES:
        raise ValidationError("A readiness result cannot mark an application submitted.")
    preparation = db.get(ApplicationPreparation, preparation_id)
    if preparation is None or preparation.candidate_id != candidate_id:
        raise NotFoundError(f"No application preparation with id={preparation_id}.")
    row = ensure_for_preparation(db, preparation)
    if row.status in _LOCKED:
        return row
    reason = _failure_text(readiness) if status is ApplicationStatus.NEEDS_REVIEW else None
    transition(row, status, failure_reason=reason)
    db.commit()
    db.refresh(row)
    return row


def transition(
    row: TrackedApplication,
    new_status: ApplicationStatus,
    *,
    failure_reason: str | None = None,
    confirmation: str | None = None,
    submitted_at: datetime | None = None,
) -> TrackedApplication:
    if new_status != row.status and new_status not in ALLOWED_TRANSITIONS[row.status]:
        raise ValidationError(f"Cannot move an application from {row.status.value} to {new_status.value}.")
    row.status = new_status
    if new_status in _NOTE_STATUSES:
        row.failure_reason = _clean(failure_reason, 500)
    else:
        row.failure_reason = None
    if new_status in _CONFIRMATION_STATUSES:
        row.confirmation = _clean(confirmation, 300)
    elif new_status is not ApplicationStatus.SUBMITTING:
        row.confirmation = None
    if new_status is ApplicationStatus.SUBMITTED:
        row.submitted_at = submitted_at or datetime.now(timezone.utc)
    elif new_status is not ApplicationStatus.CONFIRMATION_UNKNOWN:
        row.submitted_at = None
    return row


def count_for_job(db: Session, candidate_id: int, job_id: int) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(TrackedApplication)
            .where(TrackedApplication.candidate_id == candidate_id, TrackedApplication.job_id == job_id)
        ).scalar_one()
    )


def _find(db: Session, candidate_id: int, job_id: int) -> TrackedApplication | None:
    return db.execute(
        select(TrackedApplication).where(
            TrackedApplication.candidate_id == candidate_id,
            TrackedApplication.job_id == job_id,
        )
    ).scalar_one_or_none()


def _employer_name(job: Job) -> str:
    source = job.job_source
    if source is not None and source.employer is not None and source.employer.name:
        return source.employer.name
    return "Unknown employer"


def _failure_text(readiness) -> str | None:
    parts = []
    for check in getattr(readiness, "checks", []) or []:
        if getattr(check, "status", "") == "passed":
            continue
        code = getattr(check, "code", "review")
        detail = _clean(getattr(check, "detail", ""), 240) or "This check could not be verified."
        parts.append(f"{code}: {detail}")
    if not parts:
        return "The application needs review."
    return _clean(" ".join(parts), 500)


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    text = _EMAIL.sub("[redacted]", text)
    text = _LONG_NUMBER.sub("[redacted]", text)
    text = text[:limit].strip()
    return text or None
