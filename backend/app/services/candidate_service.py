"""Candidate profile + preferences business logic.

CareerPilot is local-first and single-candidate in Phase 1: the schema
supports multiple `candidates` rows for future-proofing, but this service
exposes "the" candidate as the single row with the lowest id, creating one
on first write. This keeps the API simple (`GET/PUT /api/candidate`) without
baking a single-tenant assumption into the database schema itself.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.candidate import (
    Candidate,
    CandidateLocationPreference,
    CandidatePreference,
    CandidateRolePreference,
)
from app.schemas.candidate import CandidateCreate, CandidateUpdate, PreferencesUpdate


def get_candidate(db: Session) -> Candidate | None:
    return db.execute(select(Candidate).order_by(Candidate.id).limit(1)).scalars().first()


def get_candidate_or_404(db: Session) -> Candidate:
    candidate = get_candidate(db)
    if candidate is None:
        raise NotFoundError("No candidate profile exists yet. Create one first.")
    return candidate


def create_candidate(db: Session, data: CandidateCreate) -> Candidate:
    if get_candidate(db) is not None:
        raise ConflictError("A candidate profile already exists. Use update instead of create.")

    candidate = Candidate(**data.model_dump())
    db.add(candidate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Could not create candidate: {exc.orig}") from exc
    db.refresh(candidate)
    return candidate


def update_candidate(db: Session, data: CandidateUpdate) -> Candidate:
    candidate = get_candidate_or_404(db)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(candidate, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Could not update candidate: {exc.orig}") from exc
    db.refresh(candidate)
    return candidate


def get_preferences(db: Session, candidate: Candidate) -> CandidatePreference:
    if candidate.preferences is None:
        prefs = CandidatePreference(candidate_id=candidate.id)
        db.add(prefs)
        db.commit()
        db.refresh(candidate)
    return candidate.preferences


def upsert_preferences(db: Session, candidate: Candidate, data: PreferencesUpdate) -> CandidatePreference:
    prefs = get_preferences(db, candidate)

    prefs.remote_ok = data.remote_ok
    prefs.target_employment_types = data.target_employment_types
    prefs.target_start_window_start = data.target_start_window_start
    prefs.target_start_window_end = data.target_start_window_end
    prefs.min_match_score_to_surface = data.min_match_score_to_surface

    # Replace the location/role preference lists wholesale — simpler and
    # safer than diffing, and these lists are small (a handful of rows).
    for existing in list(candidate.location_preferences):
        db.delete(existing)
    for existing in list(candidate.role_preferences):
        db.delete(existing)
    db.flush()

    for loc in data.locations:
        db.add(
            CandidateLocationPreference(
                candidate_id=candidate.id,
                label=loc.label,
                location_type=loc.location_type,
                priority=loc.priority,
            )
        )
    for role in data.roles:
        db.add(
            CandidateRolePreference(
                candidate_id=candidate.id,
                role_category=role.role_category,
                priority=role.priority,
            )
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Could not update preferences: {exc.orig}") from exc

    db.refresh(candidate)
    return candidate.preferences
