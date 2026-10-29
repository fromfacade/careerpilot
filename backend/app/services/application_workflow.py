"""Start the Greenhouse application flow for one job.

This reuses the preparation pipeline. It does not open a browser and it
does not submit. Unknown eligibility is reported and is not treated as ready.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.autofill.urls import greenhouse_application_url
from app.core.exceptions import ValidationError
from app.models.application import TrackedApplication
from app.models.candidate import Candidate
from app.models.enums import ApplicationStatus
from app.models.job import Job, JobAssessment
from app.models.preparation import ApplicationPreparation
from app.services import preparation_service
from app.services.application_tracking import find_for_preparation

_BLOCKED = {
    ApplicationStatus.SUBMITTED: "This application was already received. CareerPilot will not submit it again.",
    ApplicationStatus.CONFIRMATION_UNKNOWN: (
        "The last submission outcome is unknown. Resolve it from the application record before trying again."
    ),
    ApplicationStatus.SUBMITTING: "Another submission is already in progress for this application.",
}


@dataclass(frozen=True)
class WorkflowStart:
    preparation: ApplicationPreparation
    reused: bool
    can_open_browser: bool
    eligibility: str
    eligibility_detail: str
    message: str


def begin_workflow(db: Session, candidate: Candidate, job_id: int) -> WorkflowStart:
    job = preparation_service._load_job(db, job_id)
    _require_greenhouse(job)
    eligibility, eligibility_detail = _eligibility(db, candidate, job)
    existing = preparation_service.get_open_preparation(db, candidate, job.id)
    blocked = _blocked_message(db, candidate.id, job.id, existing)
    if blocked and existing is not None:
        return WorkflowStart(
            preparation=existing,
            reused=True,
            can_open_browser=False,
            eligibility=eligibility,
            eligibility_detail=eligibility_detail,
            message=blocked,
        )
    if blocked:
        raise ValidationError(blocked)
    reused = existing is not None
    preparation = preparation_service.create_or_get_preparation(db, candidate, job.id)
    message = _start_message(preparation, reused=reused, eligibility=eligibility, eligibility_detail=eligibility_detail)
    return WorkflowStart(
        preparation=preparation,
        reused=reused,
        can_open_browser=True,
        eligibility=eligibility,
        eligibility_detail=eligibility_detail,
        message=message,
    )


def _require_greenhouse(job: Job) -> None:
    source = job.job_source
    provider = source.provider.value if source is not None else None
    url, note = greenhouse_application_url(
        job.apply_url,
        provider=provider,
        board_token=source.board_token if source is not None else None,
        external_id=job.external_id,
    )
    if url:
        return
    if (provider or "").casefold() == "lever":
        raise ValidationError("Lever applications are not supported yet. CareerPilot did not open a browser or submit.")
    if (provider or "").casefold() == "ashby":
        raise ValidationError("Ashby applications are not supported yet. CareerPilot did not open a browser or submit.")
    raise ValidationError(note or "Only Greenhouse application pages can be filled in this version. Nothing was submitted.")


def _blocked_message(
    db: Session,
    candidate_id: int,
    job_id: int,
    preparation: ApplicationPreparation | None,
) -> str | None:
    tracked = find_for_preparation(db, preparation) if preparation is not None else None
    if tracked is None:
        tracked = db.execute(
            select(TrackedApplication).where(
                TrackedApplication.candidate_id == candidate_id,
                TrackedApplication.job_id == job_id,
            )
        ).scalar_one_or_none()
    if tracked is None:
        return None
    return _BLOCKED.get(tracked.status)


def _eligibility(db: Session, candidate: Candidate, job: Job) -> tuple[str, str]:
    assessment = db.execute(
        select(JobAssessment).where(
            JobAssessment.job_id == job.id,
            JobAssessment.candidate_id == candidate.id,
        )
    ).scalar_one_or_none()
    if assessment is None:
        return "unknown", "This job has not been checked for eligibility, so CareerPilot will not treat it as ready to submit."
    detail = ""
    reasons = assessment.eligibility_reasons or []
    if reasons and isinstance(reasons[0], dict):
        detail = str(reasons[0].get("detail") or "")
    status = assessment.eligibility.value
    if status == "unknown":
        return status, detail or "Eligibility is unknown, so CareerPilot will not submit until it can be verified."
    if status == "ineligible":
        return status, detail or "This job does not meet an eligibility rule, so CareerPilot will not submit it."
    return status, detail or "The saved eligibility check passed. The live form is checked again before submission."


def _start_message(preparation: ApplicationPreparation, *, reused: bool, eligibility: str, eligibility_detail: str) -> str:
    parts = [
        "Using the existing preparation." if reused else "Prepared this application from the job and your verified profile.",
    ]
    if preparation.resume_selection_source.value == "none":
        parts.append(preparation.resume_selection_reason or "No approved resume is available, so none was attached.")
    elif preparation.resume_selection_reason:
        parts.append(preparation.resume_selection_reason)
    if eligibility != "eligible":
        parts.append(eligibility_detail)
    parts.append("Approved fields can be filled for review. Nothing is sent until you confirm this employer and job.")
    return " ".join(part.strip() for part in parts if part and part.strip())
