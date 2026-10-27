"""Pydantic I/O for form detection and autofill plans. Neither fills nor submits."""

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
    current_value: str | None = None


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


class ProvenanceRead(BaseModel):
    kind: str
    fact_id: int | None = None
    identity_key: str | None = None
    verification_status: str | None = None
    status: str | None = None
    source_ids: list[int] = Field(default_factory=list)
    origins: list[str] = Field(default_factory=list)
    profile_field: str | None = None
    candidate_id: int | None = None


class AlternativeRead(BaseModel):
    value: str
    source_kind: str
    fact_id: int | None = None
    profile_field: str | None = None


class PlanFieldRead(BaseModel):
    field_id: str
    semantic: str
    input_type: str
    label: str
    required: bool | None
    detection_confidence: str
    proposed_value: str | None
    proposed_replacement: str | None
    existing_value: str | None
    source_fact_id: int | None
    source_kind: str | None
    mapping_confidence: str
    review_required: bool
    eligible_for_fill: bool
    uncertainty: str | None
    provenance: list[ProvenanceRead]
    alternatives: list[AlternativeRead]


class AutofillPlanRead(BaseModel):
    url: str
    supported: bool
    rejection_reason: str | None
    ready: list[PlanFieldRead]
    clarification: list[PlanFieldRead]
    missing_required: list[PlanFieldRead]
    sensitive: list[PlanFieldRead]
    unsupported: list[PlanFieldRead]
    preserve_existing: list[PlanFieldRead]
    warnings: list[str]
    blockers: list[str]


def to_plan_result(plan) -> AutofillPlanRead:
    return AutofillPlanRead.model_validate(plan, from_attributes=True)


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
