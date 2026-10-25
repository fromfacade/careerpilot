"""Maps a `JobProvider` to its adapter module's `fetch_jobs` function.

This is the only place that needs to change to add a new provider adapter.
"""

from __future__ import annotations

from collections.abc import Callable

from app.models.enums import JobProvider
from app.sources import ashby, greenhouse, lever
from app.sources.base import RawJobPosting

_ADAPTERS: dict[JobProvider, Callable[..., list[RawJobPosting]]] = {
    JobProvider.GREENHOUSE: greenhouse.fetch_jobs,
    JobProvider.LEVER: lever.fetch_jobs,
    JobProvider.ASHBY: ashby.fetch_jobs,
}


def get_adapter(provider: JobProvider) -> Callable[..., list[RawJobPosting]]:
    try:
        return _ADAPTERS[provider]
    except KeyError as exc:
        raise ValueError(f"No adapter registered for provider: {provider}") from exc
