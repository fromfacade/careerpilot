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
    is_primary: bool
    created_at: datetime


class ResumeUploadResult(BaseModel):
    """What `POST /api/resumes` returns -- upload success and parse
    success are reported as separate facts, never conflated. A 201 here
    means "the file is safely and immutably stored"; `parse_status` says
    whether structured facts could also be extracted from it."""

    resume: ResumeRead
    facts_extracted: int
    # Extracted records skipped because the candidate already verified/edited
    # an identical record.
    facts_skipped_duplicate: int = 0
    # True when a byte-identical file was already uploaded; the existing
    # resume is returned and nothing is parsed or inserted again.
    already_uploaded: bool = False


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


class CandidateFactBulkUpdate(BaseModel):
    """Explicit bulk review -- never invoked automatically. Same status
    restriction as a single-fact PATCH: cannot revert to unverified."""

    fact_ids: list[int] = Field(min_length=1, max_length=500)
    verification_status: FactVerificationStatus

    @field_validator("verification_status")
    @classmethod
    def _reject_unverified(cls, value: FactVerificationStatus) -> FactVerificationStatus:
        if value is FactVerificationStatus.UNVERIFIED:
            raise ValueError(
                "verification_status cannot be set back to 'unverified' via this endpoint; "
                "it is only ever the initial state set by extraction."
            )
        return value


class ResumeDeleteRequest(BaseModel):
    """Explicit choices for `DELETE /api/resumes/{id}`.

    Default keeps independently verified/edited facts (they are detached
    from the deleted file). `delete_verified_facts=true` is the only way
    those reviewed facts are removed. Jobs, preferences, and saved jobs
    are never referenced here.
    """

    delete_verified_facts: bool = False
    replacement_resume_id: int | None = None


class ResumeDeleteResult(BaseModel):
    deleted_resume_id: int
    facts_deleted: int
    facts_preserved: int
    primary_resume_id: int | None


class ResumeReprocessResult(BaseModel):
    """What `POST /api/resumes/{id}/reprocess` returns. The original file
    is never deleted. Only UNVERIFIED facts from that resume are replaced;
    verified / edited / rejected facts are left untouched."""

    resume: ResumeRead
    facts_extracted: int
    facts_replaced: int
    facts_preserved: int
    facts_skipped_duplicate: int = 0
