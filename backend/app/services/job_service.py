"""Job listing, save/dismiss state (module... saved/dismissed job states),
and assessment (eligibility + match score) recomputation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError
from app.models.candidate import Candidate
from app.models.job import Job, JobAssessment, JobCandidateState
from app.models.job_source import JobSource
from app.models.enums import JobState
from app.services.eligibility_service import assess_eligibility, compute_match_score


def recompute_assessment(db: Session, job: Job, candidate: Candidate) -> JobAssessment:
    eligibility, eligibility_reasons = assess_eligibility(candidate, job)
    score, match_reasons = compute_match_score(job, candidate.preferences)

    assessment = db.execute(
        select(JobAssessment).where(JobAssessment.job_id == job.id, JobAssessment.candidate_id == candidate.id)
    ).scalar_one_or_none()

    if assessment is None:
        assessment = JobAssessment(job_id=job.id, candidate_id=candidate.id)
        db.add(assessment)

    assessment.eligibility = eligibility
    assessment.eligibility_reasons = eligibility_reasons
    assessment.match_score = score
    assessment.match_reasons = match_reasons

    db.flush()
    return assessment


def recompute_all_assessments(db: Session, candidate: Candidate) -> int:
    jobs = db.execute(select(Job).where(Job.is_active.is_(True))).scalars().all()
    for job in jobs:
        recompute_assessment(db, job, candidate)
    db.commit()
    return len(jobs)


def list_jobs(
    db: Session,
    candidate: Candidate | None,
    *,
    state_filter: JobState | None = None,
    include_inactive: bool = False,
    exclude_duplicates: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> list[tuple[Job, JobState, JobAssessment | None]]:
    stmt = (
        select(Job)
        .options(
            joinedload(Job.job_source).joinedload(JobSource.employer),
            joinedload(Job.locations),
        )
        .order_by(Job.first_seen_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if not include_inactive:
        stmt = stmt.where(Job.is_active.is_(True))
    if exclude_duplicates:
        stmt = stmt.where(Job.duplicate_of_job_id.is_(None))

    jobs = list(db.execute(stmt).unique().scalars())

    results: list[tuple[Job, JobState, JobAssessment | None]] = []
    for job in jobs:
        state = JobState.NEW
        assessment: JobAssessment | None = None
        if candidate is not None:
            state_row = db.execute(
                select(JobCandidateState).where(
                    JobCandidateState.job_id == job.id, JobCandidateState.candidate_id == candidate.id
                )
            ).scalar_one_or_none()
            if state_row is not None:
                state = state_row.state

            assessment = db.execute(
                select(JobAssessment).where(
                    JobAssessment.job_id == job.id, JobAssessment.candidate_id == candidate.id
                )
            ).scalar_one_or_none()

        if state_filter is not None and state != state_filter:
            continue
        results.append((job, state, assessment))

    return results


def set_job_state(db: Session, job_id: int, candidate_id: int, state: JobState, reason: str | None) -> JobCandidateState:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found")

    state_row = db.execute(
        select(JobCandidateState).where(
            JobCandidateState.job_id == job_id, JobCandidateState.candidate_id == candidate_id
        )
    ).scalar_one_or_none()

    if state_row is None:
        state_row = JobCandidateState(job_id=job_id, candidate_id=candidate_id, state=state, state_reason=reason)
        db.add(state_row)
    else:
        state_row.state = state
        state_row.state_reason = reason

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(state_row)
    return state_row
