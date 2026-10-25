from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    Eligibility,
    EmploymentType,
    JobState,
    Relevance,
    RemoteType,
    RoleCategory,
    SeniorityLevel,
)


class JobLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_text: str
    city: str | None
    region: str | None
    country: str | None
    is_remote: bool


class JobAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    eligibility: Eligibility
    eligibility_reasons: list
    relevance: Relevance
    relevance_reasons: list
    match_score: int
    match_reasons: list
    computed_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employer_name: str
    provider: str
    title: str
    employment_type: EmploymentType
    role_category: RoleCategory
    remote_type: RemoteType
    seniority_level: SeniorityLevel
    is_non_technical: bool
    description_text: str
    apply_url: str
    canonical_url: str
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    locations: list[JobLocationRead]
    state: JobState
    assessment: JobAssessmentRead | None


class JobStateUpdate(BaseModel):
    state: JobState
    state_reason: str | None = None
