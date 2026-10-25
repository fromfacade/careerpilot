"""Rule-based, explainable eligibility checking (module 5) and match scoring
(module 6) for a (job, candidate) pair.

Every rule below returns a small, human-readable reason dict so the UI can
show *why* a job was marked eligible/ineligible or scored the way it did —
"explainable" is a hard requirement, not a nice-to-have. Nothing here uses
an LLM or opaque heuristic; it's deterministic keyword/field matching only,
which also makes it fully unit-testable without any AI provider.

Phase 1 location matching is a known simplification: there is no real
geocoding, so a small alias table maps a handful of common California/
Seattle place names to the candidate's configured location-preference
labels. This is documented here and in docs/architecture.md rather than
hidden; it is expected to improve or be replaced in a later phase.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.candidate import Candidate, CandidateLocationPreference, CandidatePreference, CandidateRolePreference
from app.models.enums import (
    Eligibility,
    EmploymentType,
    LocationPreferenceType,
    RemoteType,
    Relevance,
    SeniorityLevel,
    TriState,
)
from app.models.job import Job

_NO_SPONSORSHIP_PHRASES = [
    "not able to sponsor",
    "unable to sponsor",
    "not provide sponsorship",
    "does not sponsor",
    "will not sponsor",
    "cannot sponsor",
    "no sponsorship",
    "not sponsor visas",
    "without sponsorship",
]

_LOCATION_ALIASES: dict[str, list[str]] = {
    "california": [
        "california", " ca", ", ca", "san francisco", "sf,", "los angeles", "san jose", "santa clara",
        "sunnyvale", "mountain view", "palo alto", "santa cruz", "oakland", "san diego", "sacramento",
        "irvine", "menlo park", "cupertino", "bay area",
    ],
    "seattle": ["seattle", "bellevue", "redmond", "washington"],
}


def _reason(rule: str, result: str, detail: str) -> dict:
    return {"rule": rule, "result": result, "detail": detail}


def _assess_sponsorship(candidate: Candidate, job: Job) -> dict:
    description_lower = job.description_text.lower()
    mentions_no_sponsorship = any(phrase in description_lower for phrase in _NO_SPONSORSHIP_PHRASES)

    if candidate.requires_sponsorship == TriState.UNKNOWN and candidate.work_authorization_status.value == "unknown":
        return _reason(
            "work_authorization",
            Eligibility.UNKNOWN.value,
            "Candidate's work authorization / sponsorship need is not set in the profile.",
        )

    if candidate.requires_sponsorship == TriState.YES and mentions_no_sponsorship:
        return _reason(
            "work_authorization",
            Eligibility.INELIGIBLE.value,
            "Job posting indicates no visa sponsorship is available, and candidate profile indicates sponsorship is required.",
        )

    if candidate.requires_sponsorship == TriState.UNKNOWN:
        return _reason(
            "work_authorization",
            Eligibility.UNKNOWN.value,
            "Candidate's sponsorship requirement is not set; cannot fully verify against this posting.",
        )

    return _reason(
        "work_authorization",
        Eligibility.ELIGIBLE.value,
        "No conflict found between candidate's work authorization profile and this posting.",
    )


def _months_between(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def _assess_graduation_timing(candidate: Candidate, job: Job, today: date) -> dict | None:
    if job.employment_type == EmploymentType.NEW_GRAD:
        if candidate.graduation_date is None:
            return _reason(
                "graduation_timing",
                Eligibility.UNKNOWN.value,
                "Candidate graduation date is not set; cannot verify new-grad eligibility window.",
            )
        months_until = _months_between(candidate.graduation_date, today)
        if months_until > 12:
            return _reason(
                "graduation_timing",
                Eligibility.INELIGIBLE.value,
                f"New-grad roles typically hire within ~12 months of graduation; candidate graduates "
                f"{candidate.graduation_date.isoformat()} ({months_until} months from now).",
            )
        if months_until < -18:
            return _reason(
                "graduation_timing",
                Eligibility.INELIGIBLE.value,
                f"Candidate graduated {candidate.graduation_date.isoformat()}, outside the typical new-grad window.",
            )
        return _reason(
            "graduation_timing",
            Eligibility.ELIGIBLE.value,
            f"Candidate's graduation date ({candidate.graduation_date.isoformat()}) falls within a typical new-grad hiring window.",
        )

    if job.employment_type == EmploymentType.INTERNSHIP:
        if candidate.graduation_date is None:
            return _reason(
                "graduation_timing",
                Eligibility.UNKNOWN.value,
                "Candidate graduation date is not set; cannot verify current-student status for this internship.",
            )
        if candidate.graduation_date < today:
            return _reason(
                "graduation_timing",
                Eligibility.INELIGIBLE.value,
                f"Candidate's graduation date ({candidate.graduation_date.isoformat()}) has already passed; "
                "internships typically require current enrollment.",
            )
        return _reason(
            "graduation_timing",
            Eligibility.ELIGIBLE.value,
            "Candidate appears to be a current student, consistent with this internship posting.",
        )

    return None  # rule not applicable to this employment type


def _relevance_reason(rule: str, result: str, detail: str) -> dict:
    return {"rule": rule, "result": result, "detail": detail}


def assess_relevance(candidate: Candidate, job: Job) -> tuple[Relevance, list[dict]]:
    """Is this job in-scope for the candidate's stated career goals at all?

    Deliberately separate from `assess_eligibility` (hard application
    requirements) and from `compute_match_score` (numeric strength of fit).
    A job can be perfectly ELIGIBLE (no visa/timing blocker) and still
    NOT_RELEVANT -- e.g. a non-technical business role, or a
    director/executive-level posting, neither of which an eligibility check
    has any business opining on. See `docs/architecture.md` §6.

    This never returns RELEVANT with high confidence for roles we can't
    actually classify -- ambiguous titles (role_category == OTHER with no
    non-technical/seniority signal) come back UNKNOWN rather than a
    confident verdict in either direction.
    """
    reasons: list[dict] = []

    if job.is_non_technical:
        reasons.append(
            _relevance_reason(
                "role_scope",
                Relevance.NOT_RELEVANT.value,
                f"\"{job.title}\" looks like a non-technical position (administrative/business/sales/HR/legal/"
                "finance-style title), outside your configured technical-role scope.",
            )
        )
        return Relevance.NOT_RELEVANT, reasons

    if job.seniority_level in (
        SeniorityLevel.STAFF_OR_PRINCIPAL,
        SeniorityLevel.MANAGER_OR_DIRECTOR,
        SeniorityLevel.EXECUTIVE,
    ):
        reasons.append(
            _relevance_reason(
                "seniority",
                Relevance.NOT_RELEVANT.value,
                f"Job title indicates a {job.seniority_level.value.replace('_', ' ')} level position, which does "
                "not match an internship / new-grad / early-career profile.",
            )
        )
        return Relevance.NOT_RELEVANT, reasons

    if job.seniority_level == SeniorityLevel.SENIOR:
        reasons.append(
            _relevance_reason(
                "seniority",
                Relevance.UNKNOWN.value,
                "Job title includes a \"senior\"-style keyword; relevance to an early-career profile is uncertain "
                "rather than ruled out.",
            )
        )
        return Relevance.UNKNOWN, reasons

    if job.role_category.value == "other":
        reasons.append(
            _relevance_reason(
                "role_scope",
                Relevance.UNKNOWN.value,
                "Could not confidently classify this role as technical or non-technical from the title alone.",
            )
        )
        return Relevance.UNKNOWN, reasons

    reasons.append(
        _relevance_reason(
            "role_scope",
            Relevance.RELEVANT.value,
            f"\"{job.title}\" is a recognized technical role ({job.role_category.value}) at an "
            "early-career-appropriate seniority level.",
        )
    )
    return Relevance.RELEVANT, reasons


# A job that is NOT_RELEVANT (non-technical title, or director+ seniority)
# should never display a numerically "decent" match score just because it
# happens to be remote and full-time -- that is the exact bug reported for
# the Singapore "Administrative Business Partner" example. We keep the raw
# per-factor reasons from compute_match_score() for transparency, but add
# an explicit cap + reason so the final number can never be misleadingly
# non-trivial for an out-of-scope role.
NOT_RELEVANT_SCORE_CAP = 10


def apply_relevance_cap(score: int, reasons: list[dict], relevance: Relevance) -> tuple[int, list[dict]]:
    if relevance != Relevance.NOT_RELEVANT or score <= NOT_RELEVANT_SCORE_CAP:
        return score, reasons

    capped_reasons = reasons + [
        {
            "factor": "relevance_cap",
            "weight": None,
            "contribution": NOT_RELEVANT_SCORE_CAP - score,
            "detail": (
                f"Score capped at {NOT_RELEVANT_SCORE_CAP} because this role was classified as not relevant to "
                "your technical job search (see relevance reasons) -- a high per-factor score here would be "
                "coincidental, not meaningful."
            ),
        }
    ]
    return NOT_RELEVANT_SCORE_CAP, capped_reasons


def assess_eligibility(candidate: Candidate, job: Job) -> tuple[Eligibility, list[dict]]:
    today = datetime.now(timezone.utc).date()
    reasons = [_assess_sponsorship(candidate, job)]

    grad_reason = _assess_graduation_timing(candidate, job, today)
    if grad_reason is not None:
        reasons.append(grad_reason)

    results = {r["result"] for r in reasons}
    if Eligibility.INELIGIBLE.value in results:
        overall = Eligibility.INELIGIBLE
    elif Eligibility.UNKNOWN.value in results:
        overall = Eligibility.UNKNOWN
    else:
        overall = Eligibility.ELIGIBLE

    return overall, reasons


# --- Match scoring --------------------------------------------------------

_DEFAULT_ROLE_PRIORITY = [
    "swe_backend",
    "swe_fullstack",
    "swe_frontend",
    "infrastructure",
    "ai_engineering",
    "cybersecurity",
    "qa",
    "it_support",
    "other",
]


def _priority_weight(rank: int, max_weight: int) -> int:
    """Diminishing weight by priority rank (0 = highest priority)."""
    if rank == 0:
        return max_weight
    if rank == 1:
        return int(max_weight * 0.75)
    if rank == 2:
        return int(max_weight * 0.5)
    return int(max_weight * 0.25)


def _score_role(job: Job, role_preferences: list[CandidateRolePreference]) -> dict:
    max_weight = 40
    if role_preferences:
        ordered = sorted(role_preferences, key=lambda r: r.priority)
        for rank, pref in enumerate(ordered):
            if pref.role_category == job.role_category:
                weight = _priority_weight(rank, max_weight)
                return {
                    "factor": "role_category",
                    "weight": max_weight,
                    "contribution": weight,
                    "detail": f"Role '{job.role_category.value}' matches candidate priority #{rank + 1}.",
                }
        return {
            "factor": "role_category",
            "weight": max_weight,
            "contribution": 0,
            "detail": f"Role '{job.role_category.value}' is not in candidate's configured role priorities.",
        }

    # No preferences configured yet: fall back to the default priority order
    # from the user's stated scope (SWE/backend/full-stack first).
    try:
        rank = _DEFAULT_ROLE_PRIORITY.index(job.role_category.value)
    except ValueError:
        rank = len(_DEFAULT_ROLE_PRIORITY)
    weight = _priority_weight(min(rank, 3), max_weight)
    return {
        "factor": "role_category",
        "weight": max_weight,
        "contribution": weight,
        "detail": f"No role priorities configured; used default ordering (role '{job.role_category.value}').",
    }


def _score_location(job: Job, location_preferences: list[CandidateLocationPreference], remote_ok: bool) -> dict:
    max_weight = 30
    job_location_texts = [loc.raw_text.lower() for loc in job.locations] or ["unspecified"]

    if job.remote_type == RemoteType.REMOTE:
        remote_pref = next(
            (p for p in location_preferences if p.location_type == LocationPreferenceType.REMOTE), None
        )
        if remote_pref is not None or remote_ok:
            return {
                "factor": "location",
                "weight": max_weight,
                "contribution": max_weight,
                "detail": "Job is remote and candidate accepts remote roles.",
            }

    if not location_preferences:
        return {
            "factor": "location",
            "weight": max_weight,
            "contribution": 0,
            "detail": "No location preferences configured.",
        }

    ordered = sorted(location_preferences, key=lambda p: p.priority)
    for rank, pref in enumerate(ordered):
        aliases = _LOCATION_ALIASES.get(pref.label.lower(), [pref.label.lower()])
        if any(alias in loc_text for loc_text in job_location_texts for alias in aliases):
            weight = _priority_weight(rank, max_weight)
            return {
                "factor": "location",
                "weight": max_weight,
                "contribution": weight,
                "detail": f"Job location matches candidate priority #{rank + 1} ('{pref.label}').",
            }

    return {
        "factor": "location",
        "weight": max_weight,
        "contribution": 0,
        "detail": f"Job location ({', '.join(job_location_texts)}) did not match any configured preference.",
    }


def _score_employment_type(job: Job, target_types: list[EmploymentType]) -> dict:
    max_weight = 20
    if not target_types:
        return {
            "factor": "employment_type",
            "weight": max_weight,
            "contribution": 0,
            "detail": "No target employment types configured.",
        }
    if job.employment_type in target_types:
        return {
            "factor": "employment_type",
            "weight": max_weight,
            "contribution": max_weight,
            "detail": f"Employment type '{job.employment_type.value}' is one of the candidate's targets.",
        }
    return {
        "factor": "employment_type",
        "weight": max_weight,
        "contribution": 0,
        "detail": f"Employment type '{job.employment_type.value}' is not among the candidate's targets.",
    }


def _score_remote_alignment(job: Job, remote_ok: bool) -> dict:
    max_weight = 10
    if job.remote_type == RemoteType.REMOTE and remote_ok:
        return {
            "factor": "remote_alignment",
            "weight": max_weight,
            "contribution": max_weight,
            "detail": "Job is remote and candidate is open to remote work.",
        }
    if job.remote_type == RemoteType.REMOTE and not remote_ok:
        return {
            "factor": "remote_alignment",
            "weight": max_weight,
            "contribution": 0,
            "detail": "Job is remote but candidate preferences exclude remote work.",
        }
    return {
        "factor": "remote_alignment",
        "weight": max_weight,
        "contribution": max_weight // 2,
        "detail": f"Job remote type is '{job.remote_type.value}' (neutral).",
    }


def compute_match_score(job: Job, preferences: CandidatePreference | None) -> tuple[int, list[dict]]:
    role_preferences = preferences.candidate.role_preferences if preferences else []
    location_preferences = preferences.candidate.location_preferences if preferences else []
    remote_ok = preferences.remote_ok if preferences else True
    target_types = preferences.target_employment_types if preferences else []

    reasons = [
        _score_role(job, role_preferences),
        _score_location(job, location_preferences, remote_ok),
        _score_employment_type(job, target_types),
        _score_remote_alignment(job, remote_ok),
    ]
    total = sum(r["contribution"] for r in reasons)
    return max(0, min(100, total)), reasons
