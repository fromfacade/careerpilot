from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import FetchStatus, RunStatus, TriggerType


class DiscoveryRunSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_source_id: int
    provider: str
    board_token: str
    employer_name: str
    status: FetchStatus
    jobs_found: int
    jobs_created: int
    jobs_updated: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class DiscoveryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger_type: TriggerType
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    sources_attempted: int
    sources_succeeded: int
    jobs_created: int
    jobs_updated: int
    jobs_deactivated: int
    error_summary: str | None
    sources: list[DiscoveryRunSourceRead]
