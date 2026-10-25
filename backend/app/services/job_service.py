"""Job listing, save/dismiss state (module... saved/dismissed job states),
and assessment (eligibility + match score) recomputation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError
from app.models.candidate import Candidate
from app.models.job import Job, JobAssessment, JobCandidateState, JobLocation
from app.models.job_source import Employer, JobSource
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
from app.services.eligibility_service import (
    apply_relevance_cap,
    assess_eligibility,
    assess_relevance,
    compute_match_score,
)


def recompute_assessment(db: Session, job: Job, candidate: Candidate) -> JobAssessment:
    eligibility, eligibility_reasons = assess_eligibility(candidate, job)
    relevance, relevance_reasons = assess_relevance(candidate, job)
    score, match_reasons = compute_match_score(job, candidate.preferences)
    score, match_reasons = apply_relevance_cap(score, match_reasons, relevance)

    assessment = db.execute(
        select(JobAssessment).where(JobAssessment.job_id == job.id, JobAssessment.candidate_id == candidate.id)
    ).scalar_one_or_none()

    if assessment is None:
        assessment = JobAssessment(job_id=job.id, candidate_id=candidate.id)
        db.add(assessment)

    assessment.eligibility = eligibility
    assessment.eligibility_reasons = eligibility_reasons
    assessment.relevance = relevance
    assessment.relevance_reasons = relevance_reasons
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


# Postgres ordinal rank used by JobSort.MOST_ELIGIBLE_FIRST. NULL eligibility
# (no assessment row for this candidate yet, e.g. a brand-new job that
# hasn't been scored) does not match any WHEN clause and falls through to
# ELSE, so unscored jobs sort after INELIGIBLE but the ordering is always
# total (every job gets *some* rank) -- never silently dropped.
_ELIGIBILITY_RANK = case(
    (JobAssessment.eligibility == Eligibility.ELIGIBLE, 0),
    (JobAssessment.eligibility == Eligibility.UNKNOWN, 1),
    (JobAssessment.eligibility == Eligibility.INELIGIBLE, 2),
    else_=3,
)

# Jobs with no assessment yet (candidate=None path, or not-yet-scored) are
# treated as the lowest possible score for "highest first" and the highest
# possible score for "lowest first", so unscored jobs never accidentally
# dominate either end of a score sort.
_SCORE_FOR_DESC = func.coalesce(JobAssessment.match_score, -1)
_SCORE_FOR_ASC = func.coalesce(JobAssessment.match_score, 101)

def _state_filter_clause(states: list[JobState]):
    """`JobCandidateState.state IN (...)`, treating "no state row yet" as
    NEW (mirrors the default a freshly-discovered, never-saved-or-dismissed
    job has). Built as explicit OR conditions rather than
    `coalesce(state, 'new')` because Postgres can't implicitly match a
    native enum column against a plain VARCHAR literal in COALESCE.
    """
    conditions = [JobCandidateState.state.in_(states)]
    if JobState.NEW in states:
        conditions.append(JobCandidateState.state.is_(None))
    return or_(*conditions)


@dataclass
class ListJobsResult:
    items: list[tuple[Job, JobState, JobAssessment | None]] = field(default_factory=list)
    total: int = 0


def list_jobs(
    db: Session,
    candidate: Candidate | None,
    *,
    view: JobView = JobView.ALL,
    state_filter: JobState | None = None,
    states: list[JobState] | None = None,
    include_inactive: bool = False,
    exclude_duplicates: bool = True,
    min_score: int | None = None,
    role_categories: list[RoleCategory] | None = None,
    employment_types: list[EmploymentType] | None = None,
    remote_types: list[RemoteType] | None = None,
    eligibility: list[Eligibility] | None = None,
    relevance: list[Relevance] | None = None,
    companies: list[str] | None = None,
    location_text: str | None = None,
    posted_within_days: int | None = None,
    sort: JobSort = JobSort.SCORE_DESC,
    limit: int = 200,
    offset: int = 0,
) -> ListJobsResult:
    """List jobs for display, with all filtering/sorting/pagination done in
    SQL so it is correct and deterministic across the *entire* result set,
    not just the currently-loaded page.

    Filtering here is strictly a display concern: it never deletes or
    mutates `Job` rows. Every job discovered stays in the database
    regardless of how it's filtered here; only this query's result set
    changes.

    `view=JobView.RECOMMENDED` layers the candidate's
    `min_match_score_to_surface` preference (Priority 3's fix: this was
    previously never enforced) plus excludes `Relevance.NOT_RELEVANT` and
    dismissed jobs, *unless* the caller explicitly overrides those via
    `min_score`/`relevance`/`states`. `view=JobView.ALL` (the default)
    applies none of those automatic filters, preserving the existing
    behavior callers (including older tests) rely on.
    """
    # `state_filter` (singular) is kept only for backward compatibility with
    # existing callers; prefer `states` (plural) going forward.
    effective_states = states
    if effective_states is None and state_filter is not None:
        effective_states = [state_filter]

    effective_min_score = min_score
    effective_relevance = relevance

    if view == JobView.RECOMMENDED:
        if candidate is None:
            return ListJobsResult(items=[], total=0)
        preferences = candidate.preferences
        floor = preferences.min_match_score_to_surface if preferences is not None else 0
        effective_min_score = max(min_score, floor) if min_score is not None else floor
        if effective_relevance is None:
            effective_relevance = [Relevance.RELEVANT, Relevance.UNKNOWN]
        if effective_states is None:
            effective_states = [JobState.NEW, JobState.SAVED]

    # Score/eligibility-based sorts are meaningless without a candidate to
    # score against (there is no assessment row at all) -- fall back to a
    # sort that doesn't need one rather than referencing a table we never
    # join, which would otherwise produce an unintended cross join.
    if candidate is None and sort in (JobSort.SCORE_DESC, JobSort.SCORE_ASC, JobSort.MOST_ELIGIBLE_FIRST):
        sort = JobSort.NEWEST_FIRST

    id_query = (
        select(Job.id)
        .join(Job.job_source)
        .join(JobSource.employer)
    )

    candidate_joined = False
    if candidate is not None and (
        effective_min_score is not None
        or eligibility
        or effective_relevance
        or effective_states is not None
        or sort in (JobSort.SCORE_DESC, JobSort.SCORE_ASC, JobSort.MOST_ELIGIBLE_FIRST)
    ):
        candidate_joined = True
        id_query = id_query.outerjoin(
            JobAssessment,
            and_(JobAssessment.job_id == Job.id, JobAssessment.candidate_id == candidate.id),
        ).outerjoin(
            JobCandidateState,
            and_(JobCandidateState.job_id == Job.id, JobCandidateState.candidate_id == candidate.id),
        )

    if not include_inactive:
        id_query = id_query.where(Job.is_active.is_(True))
    if exclude_duplicates:
        id_query = id_query.where(Job.duplicate_of_job_id.is_(None))
    if role_categories:
        id_query = id_query.where(Job.role_category.in_(role_categories))
    if employment_types:
        id_query = id_query.where(Job.employment_type.in_(employment_types))
    if remote_types:
        id_query = id_query.where(Job.remote_type.in_(remote_types))
    if companies:
        id_query = id_query.where(or_(*(Employer.name.ilike(f"%{c}%") for c in companies)))
    if posted_within_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
        id_query = id_query.where(Job.posted_at.is_not(None), Job.posted_at >= cutoff)
    if location_text:
        # EXISTS rather than a JOIN: a job can have many locations, and
        # joining `job_locations` directly here would multiply Job rows,
        # which breaks both COUNT(*) and Postgres's "ORDER BY must appear
        # in SELECT list" rule for DISTINCT. EXISTS avoids both problems.
        location_match = select(JobLocation.id).where(
            JobLocation.job_id == Job.id, JobLocation.raw_text.ilike(f"%{location_text}%")
        )
        id_query = id_query.where(location_match.exists())

    if candidate_joined:
        if effective_min_score is not None:
            id_query = id_query.where(_SCORE_FOR_DESC >= effective_min_score)
        if eligibility:
            id_query = id_query.where(JobAssessment.eligibility.in_(eligibility))
        if effective_relevance:
            id_query = id_query.where(JobAssessment.relevance.in_(effective_relevance))
        if effective_states is not None:
            id_query = id_query.where(_state_filter_clause(effective_states))
    elif effective_states is not None and JobState.NEW not in effective_states:
        # No candidate loaded (or no candidate-dependent filter needed a
        # join) but the caller asked for a non-NEW state -- without a
        # candidate there is no state row to check, so nothing can match.
        return ListJobsResult(items=[], total=0)

    total = db.execute(select(func.count()).select_from(id_query.subquery())).scalar_one()

    tie_break = Job.id.asc()
    if sort == JobSort.SCORE_DESC:
        order = (_SCORE_FOR_DESC.desc(), tie_break)
    elif sort == JobSort.SCORE_ASC:
        order = (_SCORE_FOR_ASC.asc(), tie_break)
    elif sort == JobSort.MOST_ELIGIBLE_FIRST:
        order = (_ELIGIBILITY_RANK.asc(), _SCORE_FOR_DESC.desc(), tie_break)
    elif sort == JobSort.NEWEST_FIRST:
        order = (Job.posted_at.is_(None).asc(), Job.posted_at.desc(), Job.first_seen_at.desc(), tie_break)
    elif sort == JobSort.OLDEST_FIRST:
        order = (Job.posted_at.is_(None).asc(), Job.posted_at.asc(), Job.first_seen_at.asc(), tie_break)
    elif sort == JobSort.COMPANY_ASC:
        order = (func.lower(Employer.name).asc(), tie_break)
    elif sort == JobSort.COMPANY_DESC:
        order = (func.lower(Employer.name).desc(), tie_break)
    else:
        order = (tie_break,)

    paged_query = id_query.order_by(*order).offset(offset).limit(limit)
    ordered_ids = [row[0] for row in db.execute(paged_query).all()]

    if not ordered_ids:
        return ListJobsResult(items=[], total=total)

    jobs_by_id = {
        job.id: job
        for job in db.execute(
            select(Job)
            .where(Job.id.in_(ordered_ids))
            .options(
                joinedload(Job.job_source).joinedload(JobSource.employer),
                joinedload(Job.locations),
            )
        )
        .unique()
        .scalars()
    }

    states_by_job_id: dict[int, JobState] = {}
    assessments_by_job_id: dict[int, JobAssessment] = {}
    if candidate is not None:
        for state_row in db.execute(
            select(JobCandidateState).where(
                JobCandidateState.job_id.in_(ordered_ids), JobCandidateState.candidate_id == candidate.id
            )
        ).scalars():
            states_by_job_id[state_row.job_id] = state_row.state
        for assessment_row in db.execute(
            select(JobAssessment).where(
                JobAssessment.job_id.in_(ordered_ids), JobAssessment.candidate_id == candidate.id
            )
        ).scalars():
            assessments_by_job_id[assessment_row.job_id] = assessment_row

    items: list[tuple[Job, JobState, JobAssessment | None]] = []
    for job_id in ordered_ids:
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        state = states_by_job_id.get(job_id, JobState.NEW)
        assessment = assessments_by_job_id.get(job_id)
        items.append((job, state, assessment))

    return ListJobsResult(items=items, total=total)


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
