"""Auto-Apply settings. These routes do not submit an application."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.auto_apply import AutoApplyRead, AutoApplyUpdate
from app.services import auto_apply as auto_apply_service
from app.services import candidate_service

router = APIRouter(prefix="/api/candidate/auto-apply", tags=["auto-apply"])


def _candidate(db: Session):
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=AutoApplyRead)
def read_auto_apply(db: Session = Depends(get_db)):
    return auto_apply_service.read_authorization(db, _candidate(db))


@router.put("", response_model=AutoApplyRead)
def update_auto_apply(payload: AutoApplyUpdate, db: Session = Depends(get_db)):
    try:
        return auto_apply_service.save_authorization(db, _candidate(db), payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
