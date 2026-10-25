"""Normalization, deduplication-key, and rule-based inference helpers shared
by all job source adapters and the discovery service.

Job titles/descriptions/locations are untrusted third-party strings. These
functions only ever read them as plain text (never execute or render as
HTML) and are pure functions, which keeps them trivially unit-testable.
"""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.enums import EmploymentType, RemoteType, RoleCategory

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = {"gh_src", "gh_jid", "lever-source", "lever-origin", "ref", "source"}


def html_to_text(raw: str | None) -> str:
    """Best-effort plain-text extraction from (possibly entity-double-encoded)
    HTML. Not a full HTML parser — sufficient for turning job descriptions
    into readable, hashable plain text. Never used for security decisions,
    and the frontend always renders job descriptions as plain text."""
    if not raw:
        return ""
    text = raw
    # Some providers (observed: Greenhouse) return entity-escaped HTML
    # (e.g. "&lt;h2&gt;"). Unescape twice to handle both single- and
    # double-encoded input; a second pass on already-clean text is a no-op.
    text = html.unescape(html.unescape(text))
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_url(url: str) -> str:
    """Canonicalize a URL for display/dedup: lowercase scheme+host, strip
    default ports, drop known tracking query params, drop trailing slash."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[: -len(":80")]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[: -len(":443")]

    kept_params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAM_NAMES and not k.lower().startswith(_TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(kept_params)

    path = parts.path.rstrip("/") or "/"

    return urlunsplit((scheme, netloc, path, query, ""))


def compute_content_hash(title: str, description_text: str, locations: list[str]) -> str:
    normalized = "|".join([title.strip().lower(), description_text.strip().lower(), ",".join(sorted(l.strip().lower() for l in locations))])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_dedupe_key(employer_name: str, title: str, primary_location: str) -> str:
    normalized_title = _WHITESPACE_RE.sub(" ", title.strip().lower())
    normalized_location = _WHITESPACE_RE.sub(" ", primary_location.strip().lower())
    normalized = f"{employer_name.strip().lower()}|{normalized_title}|{normalized_location}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# --- Rule-based inference -----------------------------------------------
# Keyword rules are intentionally simple and transparent (not ML-based) so
# their output can be explained to the user, matching the "explainable"
# requirement for downstream match scoring. Order matters: first match wins.

_EMPLOYMENT_TYPE_KEYWORDS: list[tuple[str, EmploymentType]] = [
    ("intern", EmploymentType.INTERNSHIP),
    ("co-op", EmploymentType.INTERNSHIP),
    ("new grad", EmploymentType.NEW_GRAD),
    ("new graduate", EmploymentType.NEW_GRAD),
    ("university grad", EmploymentType.NEW_GRAD),
    ("entry level", EmploymentType.NEW_GRAD),
    ("early career", EmploymentType.NEW_GRAD),
    ("contract", EmploymentType.CONTRACT),
    ("contractor", EmploymentType.CONTRACT),
    ("temporary", EmploymentType.CONTRACT),
]

_EMPLOYMENT_TYPE_HINT_MAP: dict[str, EmploymentType] = {
    "fulltime": EmploymentType.FULL_TIME,
    "full-time": EmploymentType.FULL_TIME,
    "full_time": EmploymentType.FULL_TIME,
    "parttime": EmploymentType.CONTRACT,
    "part-time": EmploymentType.CONTRACT,
    "intern": EmploymentType.INTERNSHIP,
    "internship": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "temporary": EmploymentType.CONTRACT,
}


def infer_employment_type(title: str, raw_hint: str | None) -> EmploymentType:
    title_lower = title.lower()
    for keyword, employment_type in _EMPLOYMENT_TYPE_KEYWORDS:
        if keyword in title_lower:
            return employment_type

    if raw_hint:
        mapped = _EMPLOYMENT_TYPE_HINT_MAP.get(raw_hint.strip().lower())
        if mapped:
            return mapped

    return EmploymentType.UNKNOWN


_ROLE_CATEGORY_KEYWORDS: list[tuple[str, RoleCategory]] = [
    ("security engineer", RoleCategory.CYBERSECURITY),
    ("cybersecurity", RoleCategory.CYBERSECURITY),
    ("application security", RoleCategory.CYBERSECURITY),
    ("security analyst", RoleCategory.CYBERSECURITY),
    ("sdet", RoleCategory.QA),
    ("qa engineer", RoleCategory.QA),
    ("quality assurance", RoleCategory.QA),
    ("test engineer", RoleCategory.QA),
    ("it support", RoleCategory.IT_SUPPORT),
    ("help desk", RoleCategory.IT_SUPPORT),
    ("desktop support", RoleCategory.IT_SUPPORT),
    ("machine learning engineer", RoleCategory.AI_ENGINEERING),
    ("ml engineer", RoleCategory.AI_ENGINEERING),
    ("ai engineer", RoleCategory.AI_ENGINEERING),
    ("applied scientist", RoleCategory.AI_ENGINEERING),
    ("site reliability", RoleCategory.INFRASTRUCTURE),
    ("platform engineer", RoleCategory.INFRASTRUCTURE),
    ("infrastructure engineer", RoleCategory.INFRASTRUCTURE),
    ("devops", RoleCategory.INFRASTRUCTURE),
    ("sre", RoleCategory.INFRASTRUCTURE),
    ("full stack", RoleCategory.SWE_FULLSTACK),
    ("fullstack", RoleCategory.SWE_FULLSTACK),
    ("full-stack", RoleCategory.SWE_FULLSTACK),
    ("frontend", RoleCategory.SWE_FRONTEND),
    ("front-end", RoleCategory.SWE_FRONTEND),
    ("front end", RoleCategory.SWE_FRONTEND),
    ("backend", RoleCategory.SWE_BACKEND),
    ("back-end", RoleCategory.SWE_BACKEND),
    ("back end", RoleCategory.SWE_BACKEND),
    ("software engineer", RoleCategory.SWE_BACKEND),
    ("software developer", RoleCategory.SWE_BACKEND),
]


def infer_role_category(title: str) -> RoleCategory:
    title_lower = title.lower()
    for keyword, category in _ROLE_CATEGORY_KEYWORDS:
        if keyword in title_lower:
            return category
    return RoleCategory.OTHER


_REMOTE_HINT_MAP: dict[str, RemoteType] = {
    "remote": RemoteType.REMOTE,
    "hybrid": RemoteType.HYBRID,
    "onsite": RemoteType.ONSITE,
    "on-site": RemoteType.ONSITE,
}


def infer_remote_type(locations: list[str], raw_hint: str | None) -> RemoteType:
    if raw_hint:
        mapped = _REMOTE_HINT_MAP.get(raw_hint.strip().lower())
        if mapped:
            return mapped

    for location in locations:
        if "remote" in location.lower():
            return RemoteType.REMOTE

    return RemoteType.UNKNOWN
