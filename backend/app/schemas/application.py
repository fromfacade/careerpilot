"""Read models for tracked applications. No answer or credential fields."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApplicationEventSource, ApplicationStatus


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    previous_status: ApplicationStatus
    new_status: ApplicationStatus
    reason: str | None
    source: ApplicationEventSource
    created_at: datetime


class TrackedApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    job_id: int
    employer: str
    preparation_id: int | None
    resume_id: int | None
    status: ApplicationStatus
    submitted_at: datetime | None
    confirmation: str | None
    failure_reason: str | None
    resubmit_after: datetime | None = None
    created_at: datetime
    updated_at: datetime
    events: list[ApplicationEventRead] = Field(default_factory=list)


class ApplicationResolutionRequest(BaseModel):
    confirm: bool = False
    received: bool
    note: str = Field(min_length=1, max_length=500)
