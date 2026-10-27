"""Allow-list for application URLs. The detector never fetches these."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

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


def greenhouse_application_url(
    apply_url: str,
    *,
    provider: str | None,
    board_token: str | None,
    external_id: str | None,
) -> tuple[str | None, str]:
    """Return the Greenhouse form URL for a preparation.

    Company career pages such as stripe.com/jobs?gh_jid= are not the form.
    When the saved job came from a Greenhouse board, the board token and
    job id still identify the allow-listed application page.
    """
    decision = classify_apply_url(apply_url)
    if decision.supported:
        return decision.raw, ""
    if (provider or "").casefold() != "greenhouse":
        return None, ""
    board = (board_token or "").strip()
    job_id = (external_id or "").strip()
    if not _board(board) or not job_id.isdigit():
        return None, "This Greenhouse job is missing a board token or job id, so the application form cannot be opened."
    built = "https://boards.greenhouse.io/embed/job_app?" + urlencode({"for": board, "token": job_id})
    check = classify_apply_url(built)
    if not check.supported:
        return None, check.reason or "This Greenhouse application URL could not be built."
    return built, ""


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
