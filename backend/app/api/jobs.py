from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models.enums import (
    Eligibility,
    EmploymentType,
    JobSort,
    JobState,
    JobView,
    Relevance,
    RemoteType,
    RoleCategory,
)
from app.models.job import Job, JobAssessment, JobCandidateState
from app.models.job_source import JobSource
from app.schemas.job import JobAssessmentRead, JobRead, JobStateUpdate
from app.services import candidate_service, job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_read(job, state, assessment) -> JobRead:
    return JobRead(
        id=job.id,
        employer_name=job.job_source.employer.name,
        provider=job.job_source.provider.value,
        title=job.title,
        employment_type=job.employment_type,
        role_category=job.role_category,
        remote_type=job.remote_type,
        seniority_level=job.seniority_level,
        is_non_technical=job.is_non_technical,
        description_text=job.description_text,
        apply_url=job.apply_url,
        canonical_url=job.canonical_url,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        is_active=job.is_active,
        locations=list(job.locations),
        state=state,
        assessment=(
            JobAssessmentRead(
                eligibility=assessment.eligibility,
                eligibility_reasons=assessment.eligibility_reasons,
                relevance=assessment.relevance,
                relevance_reasons=assessment.relevance_reasons,
                match_score=assessment.match_score,
                match_reasons=assessment.match_reasons,
                computed_at=assessment.computed_at,
            )
            if assessment
            else None
        ),
    )


@router.get("", response_model=list[JobRead])
def list_jobs(
    response: Response,
    state: JobState | None = None,
    states: list[JobState] | None = Query(default=None),
    view: JobView = JobView.ALL,
    include_inactive: bool = False,
    min_score: int | None = Query(default=None, ge=0, le=100),
    role_categories: list[RoleCategory] | None = Query(default=None),
    employment_types: list[EmploymentType] | None = Query(default=None),
    remote_types: list[RemoteType] | None = Query(default=None),
    eligibility: list[Eligibility] | None = Query(default=None),
    relevance: list[Relevance] | None = Query(default=None),
    companies: list[str] | None = Query(default=None),
    location: str | None = None,
    posted_within_days: int | None = Query(default=None, ge=0),
    sort: JobSort = JobSort.SCORE_DESC,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    candidate = candidate_service.get_candidate(db)
    result = job_service.list_jobs(
        db,
        candidate,
        view=view,
        state_filter=state,
        states=states,
        include_inactive=include_inactive,
        min_score=min_score,
        role_categories=role_categories,
        employment_types=employment_types,
        remote_types=remote_types,
        eligibility=eligibility,
        relevance=relevance,
        companies=companies,
        location_text=location,
        posted_within_days=posted_within_days,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    # Total count across the *entire* filtered result set (not just this
    # page) goes in a header rather than the body, so the body stays a bare
    # `list[JobRead]` for backward compatibility with existing callers.
    response.headers["X-Total-Count"] = str(result.total)
    return [_to_read(job, state, assessment) for job, state, assessment in result.items]


@router.patch("/{job_id}/state", response_model=JobRead)
def update_job_state(job_id: int, payload: JobStateUpdate, db: Session = Depends(get_db)):
    try:
        candidate = candidate_service.get_candidate_or_404(db)
        job_service.set_job_state(db, job_id, candidate.id, payload.state, payload.state_reason)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    job = db.execute(
        select(Job)
        .options(joinedload(Job.job_source).joinedload(JobSource.employer), joinedload(Job.locations))
        .where(Job.id == job_id)
    ).unique().scalar_one()

    state_row = db.execute(
        select(JobCandidateState).where(
            JobCandidateState.job_id == job_id, JobCandidateState.candidate_id == candidate.id
        )
    ).scalar_one()
    assessment = db.execute(
        select(JobAssessment).where(JobAssessment.job_id == job_id, JobAssessment.candidate_id == candidate.id)
    ).scalar_one_or_none()

    return _to_read(job, state_row.state, assessment)
