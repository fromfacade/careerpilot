"""Read models for tracked applications. No answer or credential fields."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApplicationStatus


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
    created_at: datetime
    updated_at: datetime
