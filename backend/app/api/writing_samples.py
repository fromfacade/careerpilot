"""HTTP surface for writing samples."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import WritingSampleCategory
from app.schemas.writing_sample import WritingSampleCreate, WritingSampleRead, WritingSampleUpdate
from app.services import candidate_service, writing_sample_service

router = APIRouter(prefix="/api/candidate/writing-samples", tags=["writing-samples"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _raise(exc: Exception) -> None:
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[WritingSampleRead])
def list_writing_samples(
    category: WritingSampleCategory | None = Query(default=None),
    approved_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    candidate = _require_candidate(db)
    return writing_sample_service.list_samples(
        db, candidate, category=category, approved_only=approved_only
    )


@router.post("", response_model=WritingSampleRead, status_code=201)
def create_writing_sample(payload: WritingSampleCreate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return writing_sample_service.create_sample(
            db,
            candidate,
            body=payload.body,
            title=payload.title,
            category=payload.category,
            origin=payload.origin,
            is_approved_style_reference=payload.is_approved_style_reference,
            source_answer_id=payload.source_answer_id,
        )
    except (ConflictError, NotFoundError, ValidationError) as exc:
        _raise(exc)


@router.patch("/{sample_id}", response_model=WritingSampleRead)
def update_writing_sample(sample_id: int, payload: WritingSampleUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return writing_sample_service.update_sample(
            db,
            candidate,
            sample_id,
            title=payload.title,
            body=payload.body,
            category=payload.category,
            is_approved_style_reference=payload.is_approved_style_reference,
        )
    except (ConflictError, NotFoundError, ValidationError) as exc:
        _raise(exc)


@router.delete("/{sample_id}", status_code=204)
def delete_writing_sample(sample_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        writing_sample_service.delete_sample(db, candidate, sample_id)
    except NotFoundError as exc:
        _raise(exc)
