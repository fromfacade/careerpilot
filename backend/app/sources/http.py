"""Shared outbound HTTP helper for job source adapters.

All adapters call `get_json` instead of using `httpx` directly, so timeout,
retry/backoff, and rate-limit behavior is defined exactly once. Third-party
job board responses are untrusted: this module only ever returns parsed
JSON (dict/list) or raises `JobSourceFetchError` — it never evaluates,
executes, or renders anything from the response body.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import httpx

from app.core.exceptions import JobSourceFetchError
from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)

# Minimum seconds between requests to the same host, process-wide. A simple
# module-level dict is sufficient for a single-process local-first app; this
# is not meant to survive multiple workers.
_last_request_at: dict[str, float] = defaultdict(float)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _respect_rate_limit(host: str, min_interval_seconds: float) -> None:
    now = time.monotonic()
    elapsed = now - _last_request_at[host]
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _last_request_at[host] = time.monotonic()


def get_json(
    url: str,
    *,
    provider: str,
    board_token: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
    max_retries: int = 3,
    min_request_interval_seconds: float = 0.5,
) -> Any:
    """GET `url`, returning parsed JSON. Retries on timeouts/connection errors
    and on 429/5xx responses with exponential backoff. Raises
    JobSourceFetchError if all attempts fail."""

    host = httpx.URL(url).host
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        _respect_rate_limit(host, min_request_interval_seconds)
        try:
            response = httpx.get(url, params=params, timeout=timeout_seconds)
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning(
                "job_source_fetch_timeout",
                extra=log_extra(provider=provider, board_token=board_token, attempt=attempt, url=url),
            )
        except httpx.TransportError as exc:
            last_error = exc
            logger.warning(
                "job_source_fetch_transport_error",
                extra=log_extra(
                    provider=provider, board_token=board_token, attempt=attempt, url=url, error=str(exc)
                ),
            )
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise JobSourceFetchError(
                        provider, board_token, f"Response was not valid JSON: {exc}"
                    ) from exc
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                raise JobSourceFetchError(
                    provider,
                    board_token,
                    f"Non-retryable HTTP {response.status_code} from {url}",
                )
            last_error = httpx.HTTPStatusError(
                f"HTTP {response.status_code}", request=response.request, response=response
            )
            logger.warning(
                "job_source_fetch_retryable_status",
                extra=log_extra(
                    provider=provider,
                    board_token=board_token,
                    attempt=attempt,
                    status_code=response.status_code,
                ),
            )

        if attempt < max_retries:
            backoff_seconds = min(2 ** (attempt - 1), 8)
            time.sleep(backoff_seconds)

    raise JobSourceFetchError(
        provider, board_token, f"Failed after {max_retries} attempts: {last_error}"
    )
