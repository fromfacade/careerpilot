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


class ResumeFileFormat(str, enum.Enum):
    """The only two formats milestone 2.1 accepts. Any other extension or
    content-type is rejected at upload time (HTTP 415) before anything is
    written to disk — see app/api/resumes.py."""

    PDF = "pdf"
    DOCX = "docx"


class ResumeCategory(str, enum.Enum):
    GENERAL_SWE = "general_swe"
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    AI_ML = "ai_ml"
    CUSTOM = "custom"


class ResumeSelectionSource(str, enum.Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    FALLBACK_DEFAULT = "fallback_default"
    NONE = "none"


class ResumeParseStatus(str, enum.Enum):
    """`failed` means text extraction itself raised (corrupt/unreadable
    file) — zero facts are created, but the original upload is still
    persisted (immutability: a parse failure never loses the file). The
    SUCCESS/PARTIAL/FAILED spectrum mirrors the job-source FetchStatus
    pattern: one failure must never crash the whole request."""

    PENDING = "pending"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FactType(str, enum.Enum):
    """Categories pulled from a resume per Phase 2 objective #2. `OTHER` is
    the explicit, never-silently-dropped fallback bucket used when section
    detection can't confidently segment some or all of the document — see
    app/resume_parsing/section_parser.py."""

    EDUCATION = "education"
    SKILL = "skill"
    PROJECT = "project"
    WORK_EXPERIENCE = "work_experience"
    ACHIEVEMENT = "achievement"
    OTHER = "other"


class FactSource(str, enum.Enum):
    RESUME_EXTRACTION = "resume_extraction"
    MANUAL_ENTRY = "manual_entry"


class FactVerificationStatus(str, enum.Enum):
    """Deliberately no numeric confidence score (see docs/data-model.md).
    Every fact starts UNVERIFIED and only a human action
    (PATCH /api/candidate/facts/{id}) can move it to VERIFIED/EDITED/
    REJECTED — `verified_at` is set at that point, never automatically.
    Rejected facts are kept (status flips), never hard-deleted, matching
    this project's existing soft-state philosophy (jobs.is_active,
    duplicate_of_job_id)."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    EDITED = "edited"
    REJECTED = "rejected"


class CanonicalFactStatus(str, enum.Enum):
    """Lifecycle of an authoritative knowledge-base row.

    `active` is the one version future application automation will read.
    `conflict` is a same-identity alternative that was not silently applied.
    `archived` is a previous version the candidate chose to retire. None of
    these statuses is assigned automatically on resume parse.
    """

    ACTIVE = "active"
    CONFLICT = "conflict"
    ARCHIVED = "archived"


class CanonicalFactOrigin(str, enum.Enum):
    """How a canonical fact (or one of its provenance links) was supplied.

    Distinct from `FactSource` on extracted `candidate_facts`: a resume can
    only *propose* information; promoting it into the knowledge base is a
    separate, explicit action (`resume_import`).
    """

    RESUME_IMPORT = "resume_import"
    MANUAL_ENTRY = "manual_entry"
    PROFILE = "profile"


class AnswerCategory(str, enum.Enum):
    """Application-question buckets. Sensitive categories never receive an
    inferred value from a resume or a name; they only store what the
    candidate typed or explicitly approved.
    """

    INTEREST = "interest"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    LOGISTICS = "logistics"
    WORK_AUTHORIZATION = "work_authorization"
    SPONSORSHIP = "sponsorship"
    DISABILITY = "disability"
    VETERAN = "veteran"
    DEMOGRAPHIC = "demographic"
    CRIMINAL_HISTORY = "criminal_history"
    LEGAL_ATTESTATION = "legal_attestation"
    SALARY = "salary"
    OTHER = "other"


class AnswerStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class AnswerOrigin(str, enum.Enum):
    MANUAL = "manual"
    AI_DRAFT = "ai_draft"


class WritingTone(str, enum.Enum):
    PROFESSIONAL = "professional"
    CONVERSATIONAL = "conversational"
    FORMAL = "formal"
    PROFESSIONAL_CONVERSATIONAL = "professional_conversational"


class WritingFormality(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WritingLength(str, enum.Enum):
    SHORT = "short"
    SHORT_MEDIUM = "short_medium"
    MEDIUM = "medium"
    LONG = "long"


class WritingComplexity(str, enum.Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    VARIED = "varied"


class WritingTechnicalDetail(str, enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    SPECIFIC = "specific"
    HIGH = "high"


class WritingVocabulary(str, enum.Enum):
    STRAIGHTFORWARD = "straightforward"
    TECHNICAL = "technical"
    MIXED = "mixed"


class WritingSampleCategory(str, enum.Enum):
    TECHNICAL_EXPERIENCE = "technical_experience"
    MOTIVATION = "motivation"
    GENERAL = "general"
    OTHER = "other"


class WritingSampleOrigin(str, enum.Enum):
    """Samples are never auto-tagged as authentic user writing.

    `user_written` is typed in by the candidate. `adopted_from_answer` is an
    explicit choice to treat a revised answer as their own sample. There is
    no AI origin — an AI draft cannot become a sample without that action.
    """

    USER_WRITTEN = "user_written"
    ADOPTED_FROM_ANSWER = "adopted_from_answer"


class PreparationState(str, enum.Enum):
    """Preparation progress only — never a submission status."""

    PREPARING = "preparing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PreparationAnswerOrigin(str, enum.Enum):
    REUSED = "reused"
    ADAPTED = "adapted"
    GENERATED = "generated"


class PreparationItemStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


OPEN_PREPARATION_STATES = frozenset(
    {
        PreparationState.PREPARING,
        PreparationState.NEEDS_REVIEW,
        PreparationState.READY,
        PreparationState.FAILED,
    }
)


SENSITIVE_ANSWER_CATEGORIES = frozenset(
    {
        AnswerCategory.WORK_AUTHORIZATION,
        AnswerCategory.SPONSORSHIP,
        AnswerCategory.DISABILITY,
        AnswerCategory.VETERAN,
        AnswerCategory.DEMOGRAPHIC,
        AnswerCategory.CRIMINAL_HISTORY,
        AnswerCategory.LEGAL_ATTESTATION,
        AnswerCategory.SALARY,
    }
)
