"""Pydantic I/O for the canonical candidate knowledge base."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    CanonicalFactOrigin,
    CanonicalFactStatus,
    FactType,
    FactVerificationStatus,
)


class CanonicalFactSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_fact_id: int
    candidate_fact_id: int | None
    resume_id: int | None
    origin: CanonicalFactOrigin
    note: str | None
    created_at: datetime


class CanonicalFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    fact_type: FactType
    fact_key: str
    fact_value: dict
    identity_key: str
    status: CanonicalFactStatus
    verification_status: FactVerificationStatus
    verified_at: datetime | None
    needs_review: bool
    review_reasons: list
    conflicts_with_id: int | None
    archived_at: datetime | None
    sources: list[CanonicalFactSourceRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CanonicalFactCreate(BaseModel):
    fact_type: FactType
    fact_key: str = Field(min_length=1, max_length=300)
    fact_value: dict = Field(default_factory=dict)


class CanonicalFactUpdate(BaseModel):
    fact_key: str | None = Field(default=None, min_length=1, max_length=300)
    fact_value: dict | None = None
    verification_status: FactVerificationStatus | None = None

    @field_validator("verification_status")
    @classmethod
    def _reject_unverified(cls, value: FactVerificationStatus | None) -> FactVerificationStatus | None:
        if value is FactVerificationStatus.UNVERIFIED:
            raise ValueError("verification_status cannot be set back to 'unverified'.")
        if value is FactVerificationStatus.REJECTED:
            raise ValueError("Reject a canonical fact by archiving or deleting it.")
        return value


class CanonicalFactImportRequest(BaseModel):
    """Empty / omitted `fact_ids` imports every verified or edited extracted fact."""

    fact_ids: list[int] | None = Field(default=None, max_length=500)


class CanonicalFactImportResult(BaseModel):
    created: int
    linked: int
    conflicts: int
    skipped: int
    facts: list[CanonicalFactRead]


class CanonicalFactResolveRequest(BaseModel):
    keep: Literal["existing", "incoming"]
