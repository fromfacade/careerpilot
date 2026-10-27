"""Pydantic I/O for form detection and autofill plans. Neither fills nor submits."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AutofillDetectRequest(BaseModel):
    url: str = Field(max_length=2000)
    html: str = Field(default="", max_length=1_000_000)


class AutofillPlanRequest(AutofillDetectRequest):
    preparation_id: int | None = None


class AutofillSessionCreate(BaseModel):
    preparation_id: int


class AutofillFillRequest(BaseModel):
    included_field_ids: list[str] = Field(default_factory=list)
    overwrite_field_ids: list[str] = Field(default_factory=list)
    attach_resume: bool = True


class FieldOutcomeRead(BaseModel):
    field_id: str
    label: str
    status: str
    detail: str


class FillReportRead(BaseModel):
    outcomes: list[FieldOutcomeRead]
    resume_status: str
    resume_detail: str
    stopped: str | None = None
    submitted: bool
    unresolved: list[str]


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
    accept: str = ""


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
    name: str = ""
    element_id: str = ""
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


class ResumePlanRead(BaseModel):
    status: str
    kind: str
    preparation_id: int | None = None
    resume_id: int | None = None
    display_name: str
    file_format: str | None = None
    approved: bool
    readable: bool
    compatible: bool
    eligible_for_attach: bool
    review_required: bool
    reason: str
    field_id: str | None = None


class AnswerProposalRead(BaseModel):
    field_id: str
    label: str
    required: bool | None
    match_kind: str
    proposed_text: str | None
    proposed_replacement: str | None
    existing_value: str | None
    source: str | None = None
    source_id: int | None = None
    approval_status: str | None = None
    origin: str | None = None
    eligible_for_fill: bool
    review_required: bool
    uncertainty: str | None


class AnswerPlanRead(BaseModel):
    writing_style_profile_id: int | None = None
    answers_rewritten: bool
    matched: list[AnswerProposalRead]
    missing: list[AnswerProposalRead]
    ambiguous: list[AnswerProposalRead]
    sensitive: list[AnswerProposalRead]
    preserved: list[AnswerProposalRead]


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
    resume: ResumePlanRead
    answers: AnswerPlanRead


class AutofillSessionRead(BaseModel):
    id: str
    state: str
    preparation_id: int
    employer: str
    job_title: str
    apply_url: str
    message: str
    plan: AutofillPlanRead | None = None
    result: FillReportRead | None = None


def to_session_result(run) -> AutofillSessionRead:
    return AutofillSessionRead(
        id=run.id,
        state=run.state,
        preparation_id=run.preparation_id,
        employer=run.employer,
        job_title=run.job_title,
        apply_url=run.apply_url,
        message=run.message,
        plan=to_plan_result(run.plan) if run.plan is not None else None,
        result=FillReportRead.model_validate(run.result, from_attributes=True) if run.result is not None else None,
    )


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
