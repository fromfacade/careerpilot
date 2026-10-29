"""Tracked application status. Resolution records what the user saw. It does not submit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.local_auth import token_matches
from app.schemas.application import ApplicationResolutionRequest, TrackedApplicationRead
from app.services import application_tracking, candidate_service

router = APIRouter(prefix="/api/applications", tags=["applications"])


def require_resolution_token(x_careerpilot_token: str = Header(default="")) -> None:
    if not token_matches(x_careerpilot_token):
        raise HTTPException(status_code=401, detail="A local CareerPilot token is required to resolve an application.")


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


@router.post("/{application_id}/resolution", response_model=TrackedApplicationRead)
def resolve_application(
    application_id: int,
    payload: ApplicationResolutionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_resolution_token),
):
    try:
        return application_tracking.resolve_confirmation(
            db,
            candidate_id=_candidate_id(db),
            application_id=application_id,
            received=payload.received,
            confirm=payload.confirm,
            note=payload.note,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
