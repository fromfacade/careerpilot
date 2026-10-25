"""Lever public job board adapter.

Public, documented endpoint for a single employer's board:
https://github.com/lever/postings-api

    GET https://api.lever.co/v0/postings/{board_token}?mode=json

Returns a JSON array of postings for that board_token only — like
Greenhouse, there is no cross-company search.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.exceptions import JobSourceFetchError
from app.models.enums import JobProvider
from app.sources.base import RawJobPosting
from app.sources.http import get_json

PROVIDER = JobProvider.LEVER
_BASE_URL = "https://api.lever.co/v0/postings/{board_token}"


def _parse_epoch_millis(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def fetch_jobs(
    board_token: str,
    *,
    timeout_seconds: float = 10.0,
    max_retries: int = 3,
    min_request_interval_seconds: float = 0.5,
) -> list[RawJobPosting]:
    url = _BASE_URL.format(board_token=board_token)
    payload = get_json(
        url,
        provider=PROVIDER.value,
        board_token=board_token,
        params={"mode": "json"},
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        min_request_interval_seconds=min_request_interval_seconds,
    )

    if not isinstance(payload, list):
        raise JobSourceFetchError(PROVIDER.value, board_token, "Unexpected response shape: expected a JSON array")

    raw_jobs: list[RawJobPosting] = []
    for job in payload:
        job_id = job.get("id")
        title = job.get("text")
        if not job_id or not title:
            continue

        categories = job.get("categories") or {}
        all_locations = categories.get("allLocations") or []
        if not all_locations:
            single = categories.get("location")
            all_locations = [single] if single else []
        locations = [loc.strip() for loc in all_locations if loc and loc.strip()] or ["Unspecified"]

        apply_url = job.get("applyUrl") or job.get("hostedUrl") or ""
        canonical_url = job.get("hostedUrl") or apply_url

        raw_jobs.append(
            RawJobPosting(
                external_id=str(job_id),
                title=str(title),
                locations=locations,
                apply_url=apply_url,
                canonical_url=canonical_url,
                description_html=job.get("description"),
                description_plain=job.get("descriptionPlain"),
                posted_at=_parse_epoch_millis(job.get("createdAt")),
                employment_type_hint=categories.get("commitment"),
                remote_hint=job.get("workplaceType"),
                raw_payload=job,
            )
        )

    return raw_jobs
