"""Pydantic I/O schemas for the candidate profile + preferences API.

These are deliberately separate from the SQLAlchemy models (app/models) so
the wire format can evolve independently of storage, and so nothing in the
API layer can accidentally leak an ORM session-bound object.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import (
    DatePrecision,
    DegreeLevel,
    EmploymentType,
    LocationPreferenceType,
    RoleCategory,
    TriState,
    WorkAuthStatus,
)


class CandidateBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    school: str | None = Field(default=None, max_length=200)
    degree_level: DegreeLevel = DegreeLevel.UNKNOWN
    major: str | None = Field(default=None, max_length=200)
    graduation_date: date | None = None
    graduation_date_precision: DatePrecision = DatePrecision.UNKNOWN
    work_authorization_status: WorkAuthStatus = WorkAuthStatus.UNKNOWN
    requires_sponsorship: TriState = TriState.UNKNOWN
    current_location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    school: str | None = None
    degree_level: DegreeLevel | None = None
    major: str | None = None
    graduation_date: date | None = None
    graduation_date_precision: DatePrecision | None = None
    work_authorization_status: WorkAuthStatus | None = None
    requires_sponsorship: TriState | None = None
    current_location: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    notes: str | None = None


class CandidateRead(CandidateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class LocationPreferenceIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    location_type: LocationPreferenceType
    priority: int = 0


class LocationPreferenceOut(LocationPreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RolePreferenceIn(BaseModel):
    role_category: RoleCategory
    priority: int = 0


class RolePreferenceOut(RolePreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PreferencesUpdate(BaseModel):
    remote_ok: bool = True
    target_employment_types: list[EmploymentType] = Field(default_factory=list)
    target_start_window_start: date | None = None
    target_start_window_end: date | None = None
    min_match_score_to_surface: int = Field(default=0, ge=0, le=100)
    locations: list[LocationPreferenceIn] = Field(default_factory=list)
    roles: list[RolePreferenceIn] = Field(default_factory=list)


class PreferencesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    remote_ok: bool
    target_employment_types: list[EmploymentType]
    target_start_window_start: date | None
    target_start_window_end: date | None
    min_match_score_to_surface: int
    locations: list[LocationPreferenceOut]
    roles: list[RolePreferenceOut]
