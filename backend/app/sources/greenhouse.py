"""Greenhouse public job board adapter.

Public, documented endpoint (no API key required) for a single employer's
board: https://developers.greenhouse.io/job-board.html

    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

Returns `{"jobs": [...]}` for the given board_token only — Greenhouse's
public API does not offer a cross-company search, which is why the job
source registry exists (module 2): each employer's board is configured and
polled independently.
"""

from __future__ import annotations

from datetime import datetime

from app.core.exceptions import JobSourceFetchError
from app.models.enums import JobProvider
from app.sources.base import RawJobPosting
from app.sources.http import get_json

PROVIDER = JobProvider.GREENHOUSE
_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
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
        params={"content": "true"},
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        min_request_interval_seconds=min_request_interval_seconds,
    )

    if not isinstance(payload, dict) or "jobs" not in payload:
        raise JobSourceFetchError(PROVIDER.value, board_token, "Unexpected response shape: missing 'jobs' key")

    raw_jobs: list[RawJobPosting] = []
    for job in payload["jobs"]:
        job_id = job.get("id")
        title = job.get("title")
        if job_id is None or not title:
            continue  # untrusted input: skip malformed entries rather than crash the whole run

        # Greenhouse's `location.name` is ambiguous: for a single location it
        # is often "City, ST" (one location with a comma), but for multi-site
        # postings it can be "City1, City2, City3" (several locations joined
        # by commas, no state codes). There's no reliable way to distinguish
        # these from the string alone, so we deliberately do NOT split on
        # comma here and treat the whole string as one location — splitting
        # would sometimes wrongly turn "San Francisco, CA" into two bogus
        # locations ("San Francisco" and "CA").
        location_name = ((job.get("location") or {}).get("name") or "").strip()
        locations = [location_name] if location_name else ["Unspecified"]

        apply_url = job.get("absolute_url") or ""

        raw_jobs.append(
            RawJobPosting(
                external_id=str(job_id),
                title=str(title),
                locations=locations,
                apply_url=apply_url,
                canonical_url=apply_url,
                description_html=job.get("content"),
                description_plain=None,
                posted_at=_parse_datetime(job.get("first_published") or job.get("updated_at")),
                employment_type_hint=None,
                remote_hint=None,
                raw_payload=job,
            )
        )

    return raw_jobs
