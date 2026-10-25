"""Shared types for job source adapters.

Every provider adapter (greenhouse.py, lever.py, ashby.py) converts its
provider-specific JSON into a list of `RawJobPosting` — the one shape the
rest of the system (normalization, dedup, persistence) understands. This is
the seam that lets discovery_service stay provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class RawJobPosting:
    external_id: str
    title: str
    locations: list[str]
    apply_url: str
    canonical_url: str
    description_html: str | None
    description_plain: str | None
    posted_at: datetime | None
    employment_type_hint: str | None
    remote_hint: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class JobSourceAdapter(Protocol):
    def fetch_jobs(
        self,
        board_token: str,
        *,
        timeout_seconds: float,
        max_retries: int,
        min_request_interval_seconds: float,
    ) -> list[RawJobPosting]:
        ...
