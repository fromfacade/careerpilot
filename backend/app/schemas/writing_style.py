"""Pydantic I/O for the writing style profile."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    WritingComplexity,
    WritingFormality,
    WritingLength,
    WritingTechnicalDetail,
    WritingTone,
    WritingVocabulary,
)


class WritingStyleProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    tone: WritingTone
    formality: WritingFormality
    preferred_length: WritingLength
    sentence_complexity: WritingComplexity
    technical_detail: WritingTechnicalDetail
    vocabulary: WritingVocabulary
    phrases_to_avoid: list[str]
    additional_instructions: str
    created_at: datetime
    updated_at: datetime


class WritingStyleProfileUpdate(BaseModel):
    tone: WritingTone | None = None
    formality: WritingFormality | None = None
    preferred_length: WritingLength | None = None
    sentence_complexity: WritingComplexity | None = None
    technical_detail: WritingTechnicalDetail | None = None
    vocabulary: WritingVocabulary | None = None
    phrases_to_avoid: list[str] | None = Field(default=None, max_length=50)
    additional_instructions: str | None = Field(default=None, max_length=4000)
