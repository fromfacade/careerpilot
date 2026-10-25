from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.candidate import (
    CandidateCreate,
    CandidateRead,
    CandidateUpdate,
    PreferencesRead,
    PreferencesUpdate,
)
from app.services import candidate_service

router = APIRouter(prefix="/api/candidate", tags=["candidate"])


@router.get("", response_model=CandidateRead | None)
def read_candidate(db: Session = Depends(get_db)):
    return candidate_service.get_candidate(db)


@router.post("", response_model=CandidateRead, status_code=201)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    try:
        return candidate_service.create_candidate(db, payload)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("", response_model=CandidateRead)
def update_candidate(payload: CandidateUpdate, db: Session = Depends(get_db)):
    try:
        return candidate_service.update_candidate(db, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _to_preferences_read(prefs) -> PreferencesRead:
    return PreferencesRead(
        remote_ok=prefs.remote_ok,
        target_employment_types=prefs.target_employment_types,
        target_start_window_start=prefs.target_start_window_start,
        target_start_window_end=prefs.target_start_window_end,
        min_match_score_to_surface=prefs.min_match_score_to_surface,
        locations=prefs.candidate.location_preferences,
        roles=prefs.candidate.role_preferences,
    )


@router.get("/preferences", response_model=PreferencesRead)
def read_preferences(db: Session = Depends(get_db)):
    try:
        candidate = candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    prefs = candidate_service.get_preferences(db, candidate)
    return _to_preferences_read(prefs)


@router.put("/preferences", response_model=PreferencesRead)
def update_preferences(payload: PreferencesUpdate, db: Session = Depends(get_db)):
    try:
        candidate = candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        prefs = candidate_service.upsert_preferences(db, candidate, payload)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_preferences_read(prefs)
