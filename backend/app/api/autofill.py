"""Form detection and review plans. There is no fill or submit route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.autofill.greenhouse import detect_application
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.schemas.autofill import (
    AutofillDetectRequest,
    AutofillDetectResult,
    AutofillPlanRead,
    to_detect_result,
    to_plan_result,
)
from app.services import autofill_service, candidate_service

router = APIRouter(prefix="/api/autofill", tags=["autofill"])


@router.post("/detect", response_model=AutofillDetectResult)
def detect_application_form(payload: AutofillDetectRequest) -> AutofillDetectResult:
    return to_detect_result(detect_application(payload.url, payload.html))


@router.post("/plan", response_model=AutofillPlanRead)
def plan_application_form(payload: AutofillDetectRequest, db: Session = Depends(get_db)) -> AutofillPlanRead:
    try:
        candidate = candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_plan_result(autofill_service.build_plan(db, candidate, payload.url, payload.html))
