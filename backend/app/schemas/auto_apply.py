"""Wire format for the Auto-Apply grant. Greenhouse is the only provider."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auto_apply.authorization import ACKNOWLEDGEMENT
from app.models.enums import EmploymentType, RoleCategory


class AutoApplyResumeRead(BaseModel):
    id: int
    profile_name: str
    is_approved: bool

    model_config = ConfigDict(from_attributes=True)


class AutoApplyRead(BaseModel):
    mode: Literal["review", "auto_apply"]
    enabled: bool
    acknowledged: bool
    active: bool
    inactive_reason: str | None
    provider: Literal["greenhouse"] = "greenhouse"
    job_categories: list[RoleCategory]
    employment_types: list[EmploymentType]
    locations: list[str]
    min_match_score: int
    max_per_day: int
    max_per_session: int
    resumes: list[AutoApplyResumeRead]
    expires_at: datetime | None
    explanation: str = ACKNOWLEDGEMENT
    automatic_submission: Literal[False] = False


class AutoApplyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    acknowledge: bool = False
    provider: Literal["greenhouse"] = "greenhouse"
    job_categories: list[RoleCategory] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    min_match_score: int = Field(default=70, ge=0, le=100)
    max_per_day: int = Field(default=5, ge=0, le=25)
    max_per_session: int = Field(default=2, ge=0, le=25)
    resume_ids: list[int] = Field(default_factory=list)
    expires_at: datetime | None = None
