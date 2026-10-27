"""Pydantic I/O for application preparations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AnswerCategory,
    PreparationAnswerOrigin,
    PreparationItemStatus,
    PreparationState,
)


class PreparationAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer_text: str
    category: AnswerCategory
    origin: PreparationAnswerOrigin
    status: PreparationItemStatus
    source_answer_id: int | None
    is_sensitive: bool
    canonical_fact_ids: list
    unsupported_claims: list
    missing_information: list
    created_at: datetime
    updated_at: datetime


class ApplicationPreparationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    job_id: int | None
    source_resume_id: int | None
    state: PreparationState
    snapshot_job_title: str
    snapshot_employer: str
    snapshot_description: str
    snapshot_apply_url: str
    snapshot_content_hash: str
    analysis: dict
    match_report: dict
    tailored_resume: dict
    tailored_resume_status: PreparationItemStatus
    design_limitation: str
    error_message: str
    has_docx: bool = False
    has_pdf: bool = False
    answers: list[PreparationAnswerRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PreparationCreate(BaseModel):
    job_id: int


class PreparationAnswerUpdate(BaseModel):
    answer_text: str | None = Field(default=None, max_length=20000)
    status: PreparationItemStatus | None = None


class TailoredResumeUpdate(BaseModel):
    tailored_resume: dict | None = None
    status: PreparationItemStatus | None = None


def to_read(row) -> ApplicationPreparationRead:
    data = ApplicationPreparationRead.model_validate(row)
    return data.model_copy(update={"has_docx": bool(row.docx_path), "has_pdf": bool(row.pdf_path)})
