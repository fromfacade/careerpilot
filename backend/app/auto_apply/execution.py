"""Connect an active Auto-Apply grant to the existing submission path.

This module reloads the grant, checks the live readiness result, and holds
one limit slot. It does not open a browser or click Submit. The caller
passes a permitted reservation to the existing submit_session path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auto_apply.authorization import JobAuthorizationView, decide
from app.models.auto_apply import AutoApplyAuthorization, AutoApplyReservation
from app.models.job import Job, JobAssessment
from app.models.preparation import ApplicationPreparation
from app.models.resume import Resume
from app.services.application_tracking import find_for_preparation
from app.services.auto_apply import limit_counts, to_settings


@dataclass(frozen=True)
class ReservationResult:
    permitted: bool
    reasons: tuple[str, ...]
    reservation_id: int | None
    authorization_id: int | None


def job_view(db: Session, preparation: ApplicationPreparation, readiness, application_status: str | None) -> JobAuthorizationView:
    """Build the scope facts from stored job data and the live readiness result."""
    job = db.get(Job, preparation.job_id) if preparation.job_id is not None else None
    provider = ""
    category = ""
    employment = ""
    locations: tuple[str, ...] = ()
    remote = False
    score: int | None = None
    eligibility = "unknown"
    if job is not None:
        source = job.job_source
        provider = source.provider.value if source is not None else ""
        category = job.role_category.value
        employment = job.employment_type.value
        remote = job.remote_type.value == "remote"
        labels: list[str] = []
        for place in job.locations:
            if place.raw_text:
                labels.append(place.raw_text)
            if place.is_remote:
                remote = True
        locations = tuple(labels)
        assessment = db.scalar(
            select(JobAssessment).where(
                JobAssessment.job_id == job.id,
                JobAssessment.candidate_id == preparation.candidate_id,
            )
        )
        if assessment is not None:
            score = assessment.match_score
            eligibility = assessment.eligibility.value
    resume = db.get(Resume, preparation.source_resume_id) if preparation.source_resume_id is not None else None
    failed = tuple(
        check.code for check in getattr(readiness, "checks", []) or [] if getattr(check, "status", "") != "passed"
    )
    return JobAuthorizationView(
        provider=provider,
        role_category=category,
        employment_type=employment,
        locations=locations,
        remote=remote,
        match_score=score,
        eligibility=eligibility,
        resume_id=preparation.source_resume_id,
        resume_approved=bool(resume is not None and resume.is_approved and not resume.is_archived),
        readiness_status=getattr(readiness, "status", "") or "",
        failed_checks=failed,
        application_status=application_status,
    )


def evaluate_and_reserve(
    db: Session,
    *,
    candidate_id: int,
    preparation_id: int,
    readiness,
    now: datetime | None = None,
) -> ReservationResult:
    """Reload the grant under a row lock and hold one slot when it still permits submission."""
    current = now or datetime.now(timezone.utc)
    preparation = db.get(ApplicationPreparation, preparation_id)
    if preparation is None or preparation.candidate_id != candidate_id or preparation.job_id is None:
        return ReservationResult(False, ("This preparation is not available.",), None, None)
    authorization = db.execute(
        select(AutoApplyAuthorization)
        .where(AutoApplyAuthorization.candidate_id == candidate_id)
        .with_for_update()
    ).scalar_one_or_none()
    tracked = find_for_preparation(db, preparation)
    status = tracked.status.value if tracked is not None else None
    view = job_view(db, preparation, readiness, status)
    started = authorization.session_started_at if authorization is not None else None
    counts = limit_counts(
        db,
        candidate_id,
        started,
        current,
        exclude_application_id=tracked.id if tracked is not None else None,
    )
    decision = decide(to_settings(authorization), view, counts, current)
    authorization_id = authorization.id if authorization is not None else None
    if not decision.permitted or authorization is None or tracked is None:
        reasons = decision.reasons or ("Auto-Apply is off.",)
        return ReservationResult(False, reasons, None, authorization_id)
    existing = db.scalar(
        select(AutoApplyReservation).where(
            AutoApplyReservation.application_id == tracked.id,
            AutoApplyReservation.state == "held",
        )
    )
    if existing is not None:
        return ReservationResult(True, (), existing.id, authorization_id)
    reservation = AutoApplyReservation(
        candidate_id=candidate_id,
        authorization_id=authorization.id,
        application_id=tracked.id,
        state="held",
        created_at=current,
    )
    db.add(reservation)
    db.flush()
    return ReservationResult(True, (), reservation.id, authorization_id)


def release_reservation(db: Session, reservation_id: int | None) -> None:
    """Return a slot when the click never happened."""
    row = _held(db, reservation_id)
    if row is not None:
        row.state = "released"


def settle_reservation(db: Session, reservation_id: int | None, now: datetime | None = None) -> None:
    """Keep a slot after a click, including a definite failure or an uncertain result."""
    row = _held(db, reservation_id)
    if row is None:
        return
    row.state = "settled"
    row.settled_at = now or datetime.now(timezone.utc)


def _held(db: Session, reservation_id: int | None) -> AutoApplyReservation | None:
    if reservation_id is None:
        return None
    row = db.get(AutoApplyReservation, reservation_id)
    if row is None or row.state != "held":
        return None
    return row
