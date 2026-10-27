"""Pydantic I/O for the application answer library."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AnswerCategory, AnswerOrigin, AnswerStatus


class ApplicationAnswerFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_fact_id: int | None


class ApplicationAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    question: str
    question_fingerprint: str
    answer_text: str
    category: AnswerCategory
    status: AnswerStatus
    origin: AnswerOrigin
    is_reusable: bool
    is_preferred: bool
    is_sensitive: bool
    prefer_not_to_answer: bool
    missing_information: list
    generation_metadata: dict
    rewritten_from_id: int | None = None
    unsupported_claims: list = Field(default_factory=list)
    fact_links: list[ApplicationAnswerFactRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ApplicationAnswerCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer_text: str = Field(default="", max_length=20000)
    category: AnswerCategory = AnswerCategory.OTHER
    status: AnswerStatus = AnswerStatus.DRAFT
    is_reusable: bool = True
    is_preferred: bool = False
    prefer_not_to_answer: bool = False
    canonical_fact_ids: list[int] = Field(default_factory=list, max_length=50)


class GenerateAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    category: AnswerCategory = AnswerCategory.OTHER
    job_id: int | None = None


class ApplicationAnswerUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer_text: str | None = Field(default=None, max_length=20000)
    category: AnswerCategory | None = None
    status: AnswerStatus | None = None
    is_reusable: bool | None = None
    is_preferred: bool | None = None
    prefer_not_to_answer: bool | None = None
    canonical_fact_ids: list[int] | None = Field(default=None, max_length=50)
