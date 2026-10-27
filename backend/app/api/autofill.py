"""Form detection, review plans, and a headed Greenhouse browser.

Opening the browser and submitting require the local token. Submission
also requires an explicit confirmation for that session's preparation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.autofill.greenhouse import detect_application
from app.autofill.sessions import cancel_session, fill_session, get_session, start_session, submit_session
from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.local_auth import token_matches
from app.schemas.autofill import (
    AutofillDetectRequest,
    AutofillDetectResult,
    AutofillFillRequest,
    AutofillPlanRead,
    AutofillPlanRequest,
    AutofillSessionCreate,
    AutofillSessionRead,
    AutofillSubmitRequest,
    to_detect_result,
    to_plan_result,
    to_session_result,
)
from app.services import autofill_service, candidate_service

router = APIRouter(prefix="/api/autofill", tags=["autofill"])


def require_browser_token(x_careerpilot_token: str = Header(default="")) -> None:
    if not token_matches(x_careerpilot_token):
        raise HTTPException(status_code=401, detail="A local CareerPilot token is required to open a browser.")


@router.post("/detect", response_model=AutofillDetectResult)
def detect_application_form(payload: AutofillDetectRequest) -> AutofillDetectResult:
    return to_detect_result(detect_application(payload.url, payload.html))


@router.post("/plan", response_model=AutofillPlanRead)
def plan_application_form(payload: AutofillPlanRequest, db: Session = Depends(get_db)) -> AutofillPlanRead:
    try:
        candidate = candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_plan_result(
        autofill_service.build_plan(db, candidate, payload.url, payload.html, payload.preparation_id)
    )


@router.post("/sessions", response_model=AutofillSessionRead)
def open_autofill_session(
    payload: AutofillSessionCreate,
    _: None = Depends(require_browser_token),
) -> AutofillSessionRead:
    return to_session_result(start_session(payload.preparation_id, headed=True))


@router.get("/sessions/{session_id}", response_model=AutofillSessionRead)
def read_autofill_session(session_id: str, _: None = Depends(require_browser_token)) -> AutofillSessionRead:
    try:
        return to_session_result(get_session(session_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/fill", response_model=AutofillSessionRead)
def fill_autofill_session(
    session_id: str,
    payload: AutofillFillRequest,
    _: None = Depends(require_browser_token),
) -> AutofillSessionRead:
    try:
        run = fill_session(
            session_id,
            included=set(payload.included_field_ids),
            overwrite=set(payload.overwrite_field_ids),
            attach_resume=payload.attach_resume,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_session_result(run)


@router.post("/sessions/{session_id}/submit", response_model=AutofillSessionRead)
def submit_autofill_session(
    session_id: str,
    payload: AutofillSubmitRequest,
    _: None = Depends(require_browser_token),
) -> AutofillSessionRead:
    try:
        run = submit_session(
            session_id,
            confirm=payload.confirm,
            preparation_id=payload.preparation_id,
            apply_url=payload.apply_url,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_session_result(run)


@router.post("/sessions/{session_id}/cancel", response_model=AutofillSessionRead)
def cancel_autofill_session(session_id: str, _: None = Depends(require_browser_token)) -> AutofillSessionRead:
    try:
        return to_session_result(cancel_session(session_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
