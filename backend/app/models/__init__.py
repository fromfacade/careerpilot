"""SQLAlchemy ORM models.

Importing this package registers all models on `app.core.db.Base.metadata`,
which Alembic's `env.py` relies on for autogeneration.
"""

from app.models.candidate import Candidate, CandidateLocationPreference, CandidatePreference, CandidateRolePreference
from app.models.answer import ApplicationAnswer, ApplicationAnswerFact
from app.models.canonical import CanonicalFact, CanonicalFactSource
from app.models.discovery import DiscoveryRun, DiscoveryRunSource
from app.models.job import Job, JobAssessment, JobCandidateState, JobLocation
from app.models.job_source import Employer, JobSource
from app.models.resume import CandidateFact, Resume
from app.models.writing_style import WritingStyleProfile

__all__ = [
    "Candidate",
    "CandidatePreference",
    "CandidateLocationPreference",
    "CandidateRolePreference",
    "Employer",
    "JobSource",
    "Job",
    "JobLocation",
    "JobCandidateState",
    "JobAssessment",
    "DiscoveryRun",
    "DiscoveryRunSource",
    "Resume",
    "CandidateFact",
    "CanonicalFact",
    "CanonicalFactSource",
    "ApplicationAnswer",
    "ApplicationAnswerFact",
    "WritingStyleProfile",
]
