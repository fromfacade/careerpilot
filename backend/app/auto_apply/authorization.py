"""Opt-in Auto-Apply grant and the decision that uses it.

A permitted result means the job is inside the grant and the existing
readiness checks passed. It does not submit, and it does not change a
tracked application. Greenhouse is the only board this grant can cover.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


ACKNOWLEDGEMENT = (
    "Auto-Apply allows CareerPilot to submit eligible, complete "
    "applications automatically within your configured limits."
)
AUTHORIZED_PROVIDER = "greenhouse"
AUTOMATIC_SUBMISSION = False

_DUPLICATE_STATUS = {
    "submitting": "A submission is already in progress.",
    "submitted": "The application has already been submitted.",
    "confirmation_unknown": "Submission confirmation is unresolved.",
}

_READINESS_REASONS = {
    "graduation": "Eligibility is unknown or the candidate is not eligible.",
    "work_authorization": "Eligibility is unknown or the candidate is not eligible.",
    "required_fields": "Required application fields are incomplete.",
    "resume": "The selected resume is unapproved.",
    "approved_answers": "An application answer is unapproved.",
    "sensitive_questions": "A required sensitive or legal question needs user input.",
    "verification_challenge": "CAPTCHA or MFA is active.",
    "already_submitted": "The application has already been submitted.",
    "job_identity": "The open application is not the selected Greenhouse job.",
}


@dataclass(frozen=True)
class AutoApplySettings:
    enabled: bool
    acknowledged: bool
    expires_at: datetime | None
    job_categories: tuple[str, ...]
    employment_types: tuple[str, ...]
    locations: tuple[str, ...]
    min_match_score: int
    max_per_day: int
    max_per_session: int
    resume_ids: tuple[int, ...]

    def active(self, now: datetime) -> bool:
        return (
            self.enabled
            and self.acknowledged
            and self.expires_at is not None
            and self.expires_at > now
        )


@dataclass(frozen=True)
class JobAuthorizationView:
    """Facts the decision needs. Callers supply them; this module does not invent any."""

    provider: str
    role_category: str
    employment_type: str
    locations: tuple[str, ...]
    remote: bool
    match_score: int | None
    eligibility: str
    resume_id: int | None
    resume_approved: bool
    readiness_status: str
    failed_checks: tuple[str, ...]
    application_status: str | None


@dataclass(frozen=True)
class UsageCounts:
    submitted_today: int
    submitted_this_session: int


@dataclass(frozen=True)
class AutoApplyDecision:
    permitted: bool
    submits: bool
    reasons: tuple[str, ...]


def default_settings() -> AutoApplySettings:
    return AutoApplySettings(
        enabled=False,
        acknowledged=False,
        expires_at=None,
        job_categories=(),
        employment_types=(),
        locations=(),
        min_match_score=70,
        max_per_day=5,
        max_per_session=2,
        resume_ids=(),
    )


def decide(
    settings: AutoApplySettings,
    job: JobAuthorizationView,
    counts: UsageCounts,
    now: datetime,
) -> AutoApplyDecision:
    """Return whether a later increment could submit this job.

    `submits` is always false. Saving or evaluating a grant does not send an
    application.
    """
    reasons: list[str] = []
    if not settings.enabled:
        reasons.append("Auto-Apply is off.")
    elif not settings.acknowledged:
        reasons.append("Auto-Apply has not been explicitly acknowledged.")
    elif settings.expires_at is None or settings.expires_at <= now:
        reasons.append("The authorization has expired.")
    else:
        reasons.extend(_scope_reasons(settings, job, counts))
    unique = tuple(dict.fromkeys(reasons))
    return AutoApplyDecision(permitted=not unique, submits=AUTOMATIC_SUBMISSION, reasons=unique)


def _scope_reasons(
    settings: AutoApplySettings,
    job: JobAuthorizationView,
    counts: UsageCounts,
) -> list[str]:
    reasons: list[str] = []
    if (job.provider or "").casefold() != AUTHORIZED_PROVIDER:
        reasons.append("This job board is not authorized. Auto-Apply currently supports Greenhouse only.")
    if job.role_category not in settings.job_categories:
        reasons.append("The job category is outside the authorized categories.")
    if job.employment_type not in settings.employment_types:
        reasons.append("The employment type is outside the authorized types.")
    if not _location_matches(settings.locations, job.locations, job.remote):
        reasons.append("The job location is outside the authorized locations.")
    if job.match_score is None or job.match_score < settings.min_match_score:
        reasons.append("The match score is below the authorized minimum.")
    if counts.submitted_today >= settings.max_per_day:
        reasons.append("The daily application limit has been reached.")
    if counts.submitted_this_session >= settings.max_per_session:
        reasons.append("The session application limit has been reached.")
    if job.eligibility == "ineligible":
        reasons.append("The candidate is not eligible.")
    elif job.eligibility != "eligible":
        reasons.append("Eligibility is unknown.")
    if job.readiness_status != "ready_to_submit":
        if job.failed_checks:
            reasons.extend(
                _READINESS_REASONS.get(code, "A readiness check has not passed.") for code in job.failed_checks
            )
        else:
            reasons.append("Readiness checks have not passed.")
    if job.resume_id is None or job.resume_id not in settings.resume_ids or not job.resume_approved:
        reasons.append("The selected resume is not an approved profile in this authorization.")
    duplicate = _DUPLICATE_STATUS.get((job.application_status or "").casefold())
    if duplicate is not None:
        reasons.append(duplicate)
    return reasons


def _location_matches(authorized: tuple[str, ...], offered: tuple[str, ...], remote: bool) -> bool:
    approved = {item.strip().casefold() for item in authorized if item.strip()}
    labels = {item.strip().casefold() for item in offered if item.strip()}
    if remote:
        labels.add("remote")
    return bool(approved) and not approved.isdisjoint(labels)
