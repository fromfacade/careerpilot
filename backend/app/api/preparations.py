"""HTTP surface for application preparations. No submit endpoint exists."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.schemas.preparation import ApplicationPreparationRead, PreparationCreate, to_read
from app.services import candidate_service, preparation_service

router = APIRouter(prefix="/api/preparations", tags=["preparations"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ApplicationPreparationRead])
def list_preparations(db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    return [to_read(row) for row in preparation_service.list_preparations(db, candidate)]


@router.post("", response_model=ApplicationPreparationRead)
def create_preparation(payload: PreparationCreate, response: Response, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        existing = preparation_service.get_open_preparation(db, candidate, payload.job_id)
        row = preparation_service.create_or_get_preparation(db, candidate, payload.job_id)
        response.status_code = 200 if existing is not None else 201
        return to_read(row)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{preparation_id}", response_model=ApplicationPreparationRead)
def read_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return to_read(preparation_service.get_preparation_or_404(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{preparation_id}/cancel", response_model=ApplicationPreparationRead)
def cancel_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return to_read(preparation_service.cancel_preparation(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
