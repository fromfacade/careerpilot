"""Read API for tracked applications. There is no submit route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.schemas.application import TrackedApplicationRead
from app.services import application_tracking, candidate_service

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _candidate_id(db: Session) -> int:
    try:
        return candidate_service.get_candidate_or_404(db).id
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[TrackedApplicationRead])
def list_applications(db: Session = Depends(get_db)):
    return application_tracking.list_applications(db, _candidate_id(db))


@router.get("/{application_id}", response_model=TrackedApplicationRead)
def read_application(application_id: int, db: Session = Depends(get_db)):
    try:
        return application_tracking.get_application_or_404(db, _candidate_id(db), application_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
