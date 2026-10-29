"""Load and save the Auto-Apply grant.

Counts come from the existing tracked-application rows. This module does
not create those rows and does not move one to submitting or submitted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auto_apply.authorization import (
    AUTHORIZED_PROVIDER,
    AutoApplySettings,
    UsageCounts,
    default_settings,
)
from app.core.exceptions import ConflictError, ValidationError
from app.models.application import TrackedApplication
from app.models.auto_apply import AutoApplyAuthorization
from app.models.candidate import Candidate
from app.models.enums import ApplicationStatus, EmploymentType, RoleCategory
from app.models.resume import Resume
from app.schemas.auto_apply import AutoApplyRead, AutoApplyResumeRead, AutoApplyUpdate

_COUNTED = (ApplicationStatus.SUBMITTING, ApplicationStatus.SUBMITTED)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_authorization(db: Session, candidate: Candidate) -> AutoApplyAuthorization | None:
    return db.scalar(
        select(AutoApplyAuthorization).where(AutoApplyAuthorization.candidate_id == candidate.id)
    )


def to_settings(row: AutoApplyAuthorization | None) -> AutoApplySettings:
    if row is None:
        return default_settings()
    return AutoApplySettings(
        enabled=row.enabled,
        acknowledged=row.acknowledged,
        expires_at=row.expires_at,
        job_categories=tuple(_enum_value(item) for item in row.job_categories),
        employment_types=tuple(_enum_value(item) for item in row.employment_types),
        locations=tuple(row.locations),
        min_match_score=row.min_match_score,
        max_per_day=row.max_per_day,
        max_per_session=row.max_per_session,
        resume_ids=tuple(int(item) for item in row.resume_ids),
    )


def read_authorization(db: Session, candidate: Candidate, now: datetime | None = None) -> AutoApplyRead:
    current = now or now_utc()
    row = get_authorization(db, candidate)
    settings = to_settings(row)
    resumes = _resume_reads(db, candidate.id, settings.resume_ids)
    active = settings.active(current)
    return AutoApplyRead(
        mode="auto_apply" if active else "review",
        enabled=settings.enabled,
        acknowledged=settings.acknowledged,
        active=active,
        inactive_reason=None if active else _inactive_reason(settings, current),
        provider=AUTHORIZED_PROVIDER,
        job_categories=[RoleCategory(item) for item in settings.job_categories],
        employment_types=[EmploymentType(item) for item in settings.employment_types],
        locations=list(settings.locations),
        min_match_score=settings.min_match_score,
        max_per_day=settings.max_per_day,
        max_per_session=settings.max_per_session,
        resumes=resumes,
        expires_at=settings.expires_at,
    )


def save_authorization(
    db: Session,
    candidate: Candidate,
    data: AutoApplyUpdate,
    now: datetime | None = None,
) -> AutoApplyRead:
    current = now or now_utc()
    locations = _clean_locations(data.locations)
    categories = list(dict.fromkeys(data.job_categories))
    employment_types = list(dict.fromkeys(data.employment_types))
    resume_ids = list(dict.fromkeys(data.resume_ids))
    _require_approved_resumes(db, candidate.id, resume_ids)
    if data.enabled:
        if not data.acknowledge:
            raise ValidationError("Auto-Apply requires an explicit acknowledgement.")
        if data.expires_at is None or data.expires_at.tzinfo is None or data.expires_at <= current:
            raise ValidationError("An authorization needs an expiration time in the future.")

    row = get_authorization(db, candidate)
    if row is None:
        row = AutoApplyAuthorization(candidate_id=candidate.id)
        db.add(row)
    was_active = to_settings(row).active(current) if row.id is not None else False
    row.enabled = data.enabled
    row.job_categories = categories
    row.employment_types = employment_types
    row.locations = locations
    row.min_match_score = data.min_match_score
    row.max_per_day = data.max_per_day
    row.max_per_session = data.max_per_session
    row.resume_ids = resume_ids
    row.expires_at = data.expires_at
    if data.enabled:
        row.acknowledged = True
        if row.acknowledged_at is None:
            row.acknowledged_at = current
        if not was_active:
            row.session_started_at = current
    else:
        row.acknowledged = False
        row.session_started_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Could not save the Auto-Apply authorization.") from exc
    db.refresh(row)
    return read_authorization(db, candidate, current)


def usage_counts(db: Session, candidate_id: int, session_started_at: datetime | None, now: datetime) -> UsageCounts:
    """Count existing tracked submissions. This does not record a new one."""
    start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stamp = func.coalesce(TrackedApplication.submitted_at, TrackedApplication.updated_at)
    today = _count_since(db, candidate_id, stamp, start)
    session = _count_since(db, candidate_id, stamp, session_started_at) if session_started_at is not None else 0
    return UsageCounts(submitted_today=today, submitted_this_session=session)


def _count_since(db: Session, candidate_id: int, stamp, start: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(TrackedApplication)
            .where(
                TrackedApplication.candidate_id == candidate_id,
                TrackedApplication.status.in_(_COUNTED),
                stamp >= start,
            )
        )
        or 0
    )


def _resume_reads(db: Session, candidate_id: int, resume_ids: tuple[int, ...]) -> list[AutoApplyResumeRead]:
    if not resume_ids:
        return []
    rows = db.scalars(
        select(Resume).where(Resume.candidate_id == candidate_id, Resume.id.in_(resume_ids))
    ).all()
    by_id = {row.id: row for row in rows}
    return [
        AutoApplyResumeRead(
            id=resume_id,
            profile_name=by_id[resume_id].profile_name or "Untitled profile",
            is_approved=by_id[resume_id].is_approved and not by_id[resume_id].is_archived,
        )
        for resume_id in resume_ids
        if resume_id in by_id
    ]


def _require_approved_resumes(db: Session, candidate_id: int, resume_ids: list[int]) -> None:
    if not resume_ids:
        return
    rows = db.scalars(select(Resume).where(Resume.candidate_id == candidate_id, Resume.id.in_(resume_ids))).all()
    found = {row.id: row for row in rows}
    for resume_id in resume_ids:
        row = found.get(resume_id)
        if row is None or not row.is_approved or row.is_archived:
            raise ValidationError("An approved resume profile is required for each selected resume.")


def _clean_locations(locations: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in locations:
        label = " ".join(raw.split())
        if not label:
            continue
        if len(label) > 120:
            raise ValidationError("A location label must be 120 characters or fewer.")
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label)
    if len(cleaned) > 20:
        raise ValidationError("At most 20 locations can be authorized.")
    return cleaned


def _inactive_reason(settings: AutoApplySettings, now: datetime) -> str:
    if not settings.enabled:
        return "Auto-Apply is off."
    if not settings.acknowledged:
        return "Auto-Apply has not been explicitly acknowledged."
    return "The authorization has expired."


def _enum_value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)
