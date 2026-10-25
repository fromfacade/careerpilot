"""Python enums backing PostgreSQL native enum columns.

Every enum that represents a safety- or eligibility-relevant fact has an
explicit `UNKNOWN` member. We never use NULL to mean "don't know" for these
fields — see docs/data-model.md for the rationale.
"""

from __future__ import annotations

import enum


class DegreeLevel(str, enum.Enum):
    ASSOCIATE = "associate"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    BOOTCAMP = "bootcamp"
    OTHER = "other"
    UNKNOWN = "unknown"


class DatePrecision(str, enum.Enum):
    EXACT = "exact"
    MONTH = "month"
    UNKNOWN = "unknown"


class WorkAuthStatus(str, enum.Enum):
    US_CITIZEN = "us_citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    VISA_HOLDER = "visa_holder"
    REQUIRES_SPONSORSHIP = "requires_sponsorship"
    UNKNOWN = "unknown"


class TriState(str, enum.Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class EmploymentType(str, enum.Enum):
    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    FULL_TIME = "full_time"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


class LocationPreferenceType(str, enum.Enum):
    STATE = "state"
    METRO = "metro"
    REMOTE = "remote"


class RoleCategory(str, enum.Enum):
    SWE_BACKEND = "swe_backend"
    SWE_FRONTEND = "swe_frontend"
    SWE_FULLSTACK = "swe_fullstack"
    INFRASTRUCTURE = "infrastructure"
    AI_ENGINEERING = "ai_engineering"
    CYBERSECURITY = "cybersecurity"
    QA = "qa"
    IT_SUPPORT = "it_support"
    OTHER = "other"


class JobProvider(str, enum.Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"


class FetchStatus(str, enum.Enum):
    NEVER_RUN = "never_run"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class RemoteType(str, enum.Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class TriggerType(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class JobState(str, enum.Enum):
    NEW = "new"
    SAVED = "saved"
    DISMISSED = "dismissed"


class Eligibility(str, enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class Relevance(str, enum.Enum):
    """Whether a job falls within the candidate's stated career scope
    (technical category + an early-career-appropriate seniority level) —
    deliberately separate from `Eligibility` (hard application requirements)
    and from `match_score` (how strongly it aligns numerically). A job can
    be ELIGIBLE (no visa/timing blocker) and still NOT_RELEVANT (e.g. a
    non-technical or director-level posting), and the two must never be
    conflated in the UI. See docs/architecture.md §6."""

    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    UNKNOWN = "unknown"


class SeniorityLevel(str, enum.Enum):
    """Inferred from the job title only (keyword-based, explainable — see
    app/sources/normalize.py:infer_seniority_level). Defaults to UNKNOWN
    rather than guessing ENTRY when no seniority keyword is present, per
    the project's "never silently assume" rule for anything that feeds
    eligibility/relevance."""

    ENTRY = "entry"
    SENIOR = "senior"
    STAFF_OR_PRINCIPAL = "staff_or_principal"
    MANAGER_OR_DIRECTOR = "manager_or_director"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class JobSort(str, enum.Enum):
    """Query-param-only enum (never persisted to the DB) describing how
    `GET /api/jobs` should order the *entire* filtered result set before
    pagination — see job_service.list_jobs."""

    SCORE_DESC = "score_desc"
    SCORE_ASC = "score_asc"
    MOST_ELIGIBLE_FIRST = "most_eligible_first"
    NEWEST_FIRST = "newest_first"
    OLDEST_FIRST = "oldest_first"
    COMPANY_ASC = "company_asc"
    COMPANY_DESC = "company_desc"


class JobView(str, enum.Enum):
    """Query-param-only enum selecting which pre-baked filter set to apply
    on top of any explicit filters. ALL never excludes/deletes anything —
    it is purely a display filter; every discovered job always stays in
    the database regardless of which view is active."""

    RECOMMENDED = "recommended"
    ALL = "all"
