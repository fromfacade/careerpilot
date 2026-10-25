"""Ashby public job board adapter.

Public, documented endpoint for a single employer's board:
https://developers.ashbyhq.com/reference/jobboardapi

    GET https://api.ashbyhq.com/posting-api/job-board/{board_token}

Returns `{"jobs": [...], "apiVersion": ...}` for that board_token only.
"""

from __future__ import annotations

from datetime import datetime

from app.core.exceptions import JobSourceFetchError
from app.models.enums import JobProvider
from app.sources.base import RawJobPosting
from app.sources.http import get_json

PROVIDER = JobProvider.ASHBY
_BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{board_token}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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
        if not job_id or not title:
            continue
        if job.get("isListed") is False:
            continue  # unlisted postings are not meant to be publicly surfaced

        locations = [job.get("location")] if job.get("location") else []
        for secondary in job.get("secondaryLocations") or []:
            loc = secondary.get("location")
            if loc:
                locations.append(loc)
        locations = [loc.strip() for loc in locations if loc and loc.strip()] or ["Unspecified"]

        apply_url = job.get("applyUrl") or job.get("jobUrl") or ""
        canonical_url = job.get("jobUrl") or apply_url

        raw_jobs.append(
            RawJobPosting(
                external_id=str(job_id),
                title=str(title),
                locations=locations,
                apply_url=apply_url,
                canonical_url=canonical_url,
                description_html=job.get("descriptionHtml"),
                description_plain=job.get("descriptionPlain"),
                posted_at=_parse_datetime(job.get("publishedAt")),
                employment_type_hint=job.get("employmentType"),
                remote_hint=job.get("workplaceType"),
                raw_payload=job,
            )
        )

    return raw_jobs
