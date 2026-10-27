"""Form detection only. There is no fill or submit route."""

from __future__ import annotations

from fastapi import APIRouter

from app.autofill.greenhouse import detect_application
from app.schemas.autofill import AutofillDetectRequest, AutofillDetectResult, to_detect_result

router = APIRouter(prefix="/api/autofill", tags=["autofill"])


@router.post("/detect", response_model=AutofillDetectResult)
def detect_application_form(payload: AutofillDetectRequest) -> AutofillDetectResult:
    return to_detect_result(detect_application(payload.url, payload.html))
