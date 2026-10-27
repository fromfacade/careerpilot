"""Pydantic I/O for application-form detection. Detection does not fill or submit."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AutofillDetectRequest(BaseModel):
    url: str = Field(max_length=2000)
    html: str = Field(default="", max_length=1_000_000)


class DetectedFieldRead(BaseModel):
    field_id: str
    semantic: str
    input_type: str
    label: str
    required: bool | None
    options: list[str]
    name: str
    element_id: str
    confidence: str


class AutofillDetectResult(BaseModel):
    url: str
    provider: str
    supported: bool
    rejection_reason: str | None
    form_found: bool
    fields: list[DetectedFieldRead]
    warnings: list[str]
    blockers: list[str]
    board_token: str | None = None
    job_id: str | None = None


def to_detect_result(detection) -> AutofillDetectResult:
    return AutofillDetectResult(
        url=detection.url,
        provider=detection.provider,
        supported=detection.supported,
        rejection_reason=detection.rejection_reason,
        form_found=detection.form_found,
        fields=[DetectedFieldRead.model_validate(field, from_attributes=True) for field in detection.fields],
        warnings=detection.warnings,
        blockers=detection.blockers,
        board_token=detection.board_token,
        job_id=detection.job_id,
    )
