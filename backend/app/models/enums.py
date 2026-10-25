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
