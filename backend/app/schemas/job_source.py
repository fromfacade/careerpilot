from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FetchStatus, JobProvider


class EmployerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    careers_url: str | None = None
    notes: str | None = None


class EmployerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    careers_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class JobSourceCreate(BaseModel):
    employer_name: str = Field(min_length=1, max_length=200, description="Created if it doesn't already exist")
    provider: JobProvider
    board_token: str = Field(min_length=1, max_length=200)
    is_enabled: bool = True
    fetch_interval_minutes: int = Field(default=180, ge=5, le=1440)


class JobSourceUpdate(BaseModel):
    is_enabled: bool | None = None
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=1440)


class JobSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employer_id: int
    employer_name: str
    provider: JobProvider
    board_token: str
    is_enabled: bool
    fetch_interval_minutes: int
    last_fetched_at: datetime | None
    last_fetch_status: FetchStatus
    last_fetch_error: str | None
    created_at: datetime
    updated_at: datetime
