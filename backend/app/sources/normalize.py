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

from app.models.enums import EmploymentType, RemoteType, RoleCategory, SeniorityLevel

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


# --- Seniority + "is this a technical role at all" inference -------------
# These feed `Relevance` (app/services/eligibility_service.py), which is
# kept deliberately separate from `Eligibility`: a non-technical or
# director-level posting is not a "hard requirement" failure, it's simply
# out of scope for an early-career technical job search. Keyword rules are
# intentionally simple/transparent, not ML-based, same rationale as the
# role-category rules above. Order matters within each list: first match
# wins. Known simplification: a handful of ambiguous titles (e.g. "Lead
# Product Manager" vs "Engineering Lead") may be misclassified; this is a
# title-only heuristic, not a parse of the full job description.

_EXECUTIVE_KEYWORDS = ["chief ", "chief technology", " cto ", " ceo ", " coo ", " cfo ", "vice president", " vp ", " vp,", "president"]
_MANAGER_OR_DIRECTOR_KEYWORDS = ["director", "head of", "engineering manager", "people manager", " manager"]
_STAFF_OR_PRINCIPAL_KEYWORDS = ["principal ", "staff ", "distinguished "]
_SENIOR_KEYWORDS = ["senior ", "sr. ", "sr ", " lead ", "lead "]

# Checked in this order: most senior signal wins if a title (unusually)
# contains multiple keywords, e.g. "Senior Director" -> manager_or_director.
_SENIORITY_RULES: list[tuple[list[str], SeniorityLevel]] = [
    (_EXECUTIVE_KEYWORDS, SeniorityLevel.EXECUTIVE),
    (_MANAGER_OR_DIRECTOR_KEYWORDS, SeniorityLevel.MANAGER_OR_DIRECTOR),
    (_STAFF_OR_PRINCIPAL_KEYWORDS, SeniorityLevel.STAFF_OR_PRINCIPAL),
    (_SENIOR_KEYWORDS, SeniorityLevel.SENIOR),
]

# Deliberately excludes titles like "account manager", "product manager" is
# NOT excluded (genuinely a people/strategy leadership signal worth
# surfacing), but we do avoid over-matching generic "manager" substrings
# inside unrelated words by requiring a leading space/boundary above.
_MANAGER_FALSE_POSITIVE_GUARDS = ["account manager", "office manager"]


def infer_seniority_level(title: str) -> SeniorityLevel:
    title_lower = f" {title.lower()} "  # pad so leading-space keyword checks match at string start too

    if any(guard in title_lower for guard in _MANAGER_FALSE_POSITIVE_GUARDS):
        # "Account Manager" / "Office Manager" are not people-management
        # seniority signals in the sense we care about here. Strip the
        # generic "manager" keyword's match for these titles and fall
        # through to the remaining rules (most such titles end up UNKNOWN,
        # which is correct — we don't actually know their seniority).
        remaining_rules = [(kws, lvl) for kws, lvl in _SENIORITY_RULES if lvl != SeniorityLevel.MANAGER_OR_DIRECTOR]
    else:
        remaining_rules = _SENIORITY_RULES

    for keywords, level in remaining_rules:
        if any(keyword in title_lower for keyword in keywords):
            return level
    return SeniorityLevel.UNKNOWN


# Non-technical role keywords: deliberately scoped to clearly
# administrative/business/sales/HR/legal/finance titles, matching the
# user's stated technical-only scope (SWE/backend/full-stack/infra/AI
# engineering/cybersecurity/QA/IT support). Ambiguous roles (e.g. product
# management, design) are intentionally NOT flagged here to avoid false
# positives — they fall through to RoleCategory.OTHER and an UNKNOWN
# relevance signal instead of a confident NOT_RELEVANT one.
_NON_TECHNICAL_KEYWORDS = [
    "business partner",
    "administrative",
    "executive assistant",
    "office manager",
    "chief of staff",
    "recruiter",
    "recruiting",
    "talent acquisition",
    "sourcer",
    "sales",
    "account executive",
    "account manager",
    "business development",
    "marketing",
    "communications",
    "public relations",
    "copywriter",
    "paralegal",
    "legal counsel",
    "attorney",
    "human resources",
    " hr ",
    "people operations",
    "people ops",
    "accountant",
    "accounting",
    "bookkeeper",
    "payroll",
    "procurement",
    "facilities",
    "real estate",
    "customer success",
    "customer support",
]


def infer_is_non_technical(title: str) -> bool:
    title_lower = f" {title.lower()} "
    return any(keyword in title_lower for keyword in _NON_TECHNICAL_KEYWORDS)
