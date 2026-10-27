"""Allow-list for application URLs. The detector never fetches these."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, parse_qs

_GREENHOUSE_HOSTS = frozenset(
    {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "boards.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    }
)
_LEVER_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})
_ASHBY_HOSTS = frozenset({"jobs.ashbyhq.com"})
_MAX_URL_LENGTH = 2000


@dataclass(frozen=True)
class ApplyUrl:
    raw: str
    supported: bool
    provider: str
    reason: str
    board_token: str | None = None
    job_id: str | None = None


def navigation_allowed(url: str) -> bool:
    """True for a Greenhouse document navigation, including redirects on those hosts."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in {None, 443}:
        return False
    host = (parts.hostname or "").casefold().rstrip(".")
    return host in _GREENHOUSE_HOSTS


def classify_apply_url(url: str) -> ApplyUrl:
    raw = (url or "").strip()
    if not raw or len(raw) > _MAX_URL_LENGTH:
        return ApplyUrl(raw, False, "unknown", "Enter a Greenhouse application URL.")
    if any(char in raw for char in ("\n", "\r", "\t")):
        return ApplyUrl(raw, False, "unknown", "That URL is not a supported application link.")

    parts = urlsplit(raw)
    if parts.username or parts.password:
        return ApplyUrl(raw, False, "unknown", "URLs with embedded credentials are rejected.")
    host = (parts.hostname or "").casefold().rstrip(".")
    if parts.scheme != "https" or not host or parts.port not in {None, 443}:
        return ApplyUrl(raw, False, "unknown", "Application URLs must use https on the default port.")

    if host in _LEVER_HOSTS:
        return ApplyUrl(raw, False, "lever", "Lever applications are not supported yet.")
    if host in _ASHBY_HOSTS:
        return ApplyUrl(raw, False, "ashby", "Ashby applications are not supported yet.")
    if host not in _GREENHOUSE_HOSTS:
        if "greenhouse" in host:
            return ApplyUrl(raw, False, "unknown", "That host is not an allow-listed Greenhouse domain.")
        return ApplyUrl(raw, False, "unknown", "Only Greenhouse application pages can be detected in this version.")

    job = _greenhouse_job(parts.path, parse_qs(parts.query))
    if job is None:
        return ApplyUrl(raw, False, "greenhouse", "That Greenhouse URL is not a single job application.")
    board, job_id = job
    return ApplyUrl(raw, True, "greenhouse", "", board_token=board, job_id=job_id)


def _greenhouse_job(path: str, query: dict[str, list[str]]) -> tuple[str, str] | None:
    pieces = [piece for piece in path.split("/") if piece and piece not in {".", ".."}]
    if len(pieces) >= 3 and pieces[1] == "jobs" and pieces[2].isdigit() and _board(pieces[0]):
        return pieces[0], pieces[2]
    if pieces == ["embed", "job_app"]:
        board = (query.get("for") or [""])[0]
        job_id = (query.get("token") or [""])[0]
        if _board(board) and job_id.isdigit():
            return board, job_id
    return None


def _board(value: str) -> bool:
    return bool(value) and value.replace("-", "").replace("_", "").isalnum()
