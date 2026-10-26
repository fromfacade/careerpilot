"""Pydantic I/O schemas for resume upload and the candidate fact vault."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import FactSource, FactType, FactVerificationStatus, ResumeFileFormat, ResumeParseStatus


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    original_filename: str
    file_format: ResumeFileFormat
    file_size_bytes: int
    sha256_checksum: str
    parse_status: ResumeParseStatus
    parse_error: str | None
    created_at: datetime


class ResumeUploadResult(BaseModel):
    """What `POST /api/resumes` returns -- upload success and parse
    success are reported as separate facts, never conflated. A 201 here
    means "the file is safely and immutably stored"; `parse_status` says
    whether structured facts could also be extracted from it."""

    resume: ResumeRead
    facts_extracted: int


class CandidateFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    resume_id: int | None
    fact_type: FactType
    fact_key: str
    fact_value: dict
    raw_text: str | None
    source: FactSource
    verification_status: FactVerificationStatus
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CandidateFactUpdate(BaseModel):
    """The only mutation path for a fact -- human review via
    `PATCH /api/candidate/facts/{id}`. `verification_status` may only be
    set to VERIFIED/EDITED/REJECTED (never back to UNVERIFIED, and
    `source` can never be changed here) -- see app/models/enums.py."""

    fact_key: str | None = Field(default=None, min_length=1, max_length=300)
    fact_value: dict | None = None
    verification_status: FactVerificationStatus | None = None

    @field_validator("verification_status")
    @classmethod
    def _reject_unverified(cls, value: FactVerificationStatus | None) -> FactVerificationStatus | None:
        if value is FactVerificationStatus.UNVERIFIED:
            raise ValueError(
                "verification_status cannot be set back to 'unverified' via this endpoint; "
                "it is only ever the initial state set by extraction."
            )
        return value
