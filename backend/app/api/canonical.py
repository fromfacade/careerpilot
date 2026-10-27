"""HTTP surface for the canonical candidate knowledge base.

Thin: validate, call one service method, map exceptions. No SQL here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import CanonicalFactStatus, FactType, FactVerificationStatus
from app.schemas.canonical import (
    CanonicalFactCreate,
    CanonicalFactImportRequest,
    CanonicalFactImportResult,
    CanonicalFactRead,
    CanonicalFactResolveRequest,
    CanonicalFactUpdate,
)
from app.services import candidate_service, canonical_service

router = APIRouter(prefix="/api/candidate/canonical-facts", tags=["canonical-facts"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[CanonicalFactRead])
def list_canonical_facts(
    fact_type: FactType | None = Query(default=None),
    status: CanonicalFactStatus | None = Query(default=None),
    verification_status: FactVerificationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    candidate = _require_candidate(db)
    return canonical_service.list_canonical_facts(
        db, candidate, fact_type=fact_type, status=status, verification_status=verification_status
    )


@router.post("", response_model=CanonicalFactRead, status_code=201)
def create_canonical_fact(payload: CanonicalFactCreate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return canonical_service.create_manual_fact(
            db,
            candidate,
            fact_type=payload.fact_type,
            fact_key=payload.fact_key,
            fact_value=payload.fact_value,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/import", response_model=CanonicalFactImportResult)
def import_verified_facts(payload: CanonicalFactImportRequest, db: Session = Depends(get_db)):
    """Promote verified/edited extracted facts. Never overwrites an active value."""
    candidate = _require_candidate(db)
    try:
        outcome = canonical_service.import_verified_facts(db, candidate, fact_ids=payload.fact_ids)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CanonicalFactImportResult(
        created=outcome.created,
        linked=outcome.linked,
        conflicts=outcome.conflicts,
        skipped=outcome.skipped,
        facts=[CanonicalFactRead.model_validate(f) for f in outcome.facts],
    )


@router.get("/{fact_id}", response_model=CanonicalFactRead)
def read_canonical_fact(fact_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return canonical_service.get_canonical_fact_or_404(db, candidate, fact_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{fact_id}", response_model=CanonicalFactRead)
def update_canonical_fact(fact_id: int, payload: CanonicalFactUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return canonical_service.update_canonical_fact(
            db,
            candidate,
            fact_id,
            fact_key=payload.fact_key,
            fact_value=payload.fact_value,
            verification_status=payload.verification_status,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConflictError, ValidationError) as exc:
        status = 409 if isinstance(exc, ConflictError) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/{fact_id}/archive", response_model=CanonicalFactRead)
def archive_canonical_fact(fact_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return canonical_service.archive_canonical_fact(db, candidate, fact_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{fact_id}/resolve", response_model=CanonicalFactRead)
def resolve_canonical_conflict(
    fact_id: int, payload: CanonicalFactResolveRequest, db: Session = Depends(get_db)
):
    candidate = _require_candidate(db)
    try:
        return canonical_service.resolve_conflict(db, candidate, fact_id, keep=payload.keep)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{fact_id}", status_code=204)
def delete_canonical_fact(fact_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        canonical_service.delete_canonical_fact(db, candidate, fact_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
