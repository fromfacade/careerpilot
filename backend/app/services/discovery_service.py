"""Discovery orchestration (modules 2-4): fetch each enabled job source,
normalize + deduplicate postings, persist them, and record a `DiscoveryRun`
with per-source detail.

This module is the single entry point both the manual "Run discovery" API
endpoint and the APScheduler job call — there is exactly one code path for
discovery, so behavior can't silently diverge between manual and scheduled
runs.

Phase 1 runs discovery synchronously within the calling request/job. This
is a deliberate simplicity choice for a local-first app polling a handful of
boards; if the number of sources grows large enough to make this slow, the
natural evolution is a background task queue, without changing this
module's public functions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.exceptions import ConflictError, JobSourceFetchError
from app.core.logging import get_logger, log_extra
from app.models.discovery import DiscoveryRun, DiscoveryRunSource
from app.models.enums import FetchStatus, RunStatus, TriggerType
from app.models.job import Job, JobLocation
from app.models.job_source import JobSource
from app.sources import normalize
from app.sources.base import RawJobPosting
from app.sources.registry import get_adapter

logger = get_logger(__name__)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _replace_locations(db: Session, job: Job, location_strings: list[str]) -> None:
    for existing in list(job.locations):
        db.delete(existing)
    db.flush()
    # Real-world providers (observed: Ashby) sometimes list the same office
    # in both the primary `location` and `secondaryLocations` fields; dedupe
    # defensively here regardless of which adapter produced the list, since
    # (job_id, raw_text) is a unique constraint.
    for raw_text in _dedupe_preserving_order(location_strings):
        db.add(
            JobLocation(
                job_id=job.id,
                raw_text=raw_text,
                is_remote="remote" in raw_text.lower(),
            )
        )


def _upsert_job(db: Session, job_source: JobSource, employer_name: str, raw: RawJobPosting, now: datetime) -> tuple[Job, bool]:
    description_text = raw.description_plain or normalize.html_to_text(raw.description_html)
    employment_type = normalize.infer_employment_type(raw.title, raw.employment_type_hint)
    role_category = normalize.infer_role_category(raw.title)
    remote_type = normalize.infer_remote_type(raw.locations, raw.remote_hint)
    seniority_level = normalize.infer_seniority_level(raw.title)
    is_non_technical = normalize.infer_is_non_technical(raw.title)
    canonical_url = normalize.normalize_url(raw.canonical_url or raw.apply_url)
    apply_url = raw.apply_url or raw.canonical_url
    content_hash = normalize.compute_content_hash(raw.title, description_text, raw.locations)
    primary_location = raw.locations[0] if raw.locations else "Unspecified"
    dedupe_key = normalize.compute_dedupe_key(employer_name, raw.title, primary_location)

    existing = db.execute(
        select(Job).where(Job.job_source_id == job_source.id, Job.external_id == raw.external_id)
    ).scalar_one_or_none()

    if existing is not None:
        existing.last_seen_at = now
        existing.is_active = True
        if existing.content_hash != content_hash:
            existing.title = raw.title
            existing.description_text = description_text
            existing.employment_type = employment_type
            existing.role_category = role_category
            existing.remote_type = remote_type
            existing.seniority_level = seniority_level
            existing.is_non_technical = is_non_technical
            existing.apply_url = apply_url
            existing.canonical_url = canonical_url
            existing.content_hash = content_hash
            existing.dedupe_key = dedupe_key
            existing.posted_at = raw.posted_at
            existing.raw_payload = raw.raw_payload
            _replace_locations(db, existing, raw.locations)
        return existing, False

    duplicate_of_job_id = db.execute(
        select(Job.id).where(
            Job.dedupe_key == dedupe_key,
            Job.is_active.is_(True),
            Job.job_source_id != job_source.id,
        )
    ).scalars().first()

    job = Job(
        job_source_id=job_source.id,
        external_id=raw.external_id,
        title=raw.title,
        employment_type=employment_type,
        role_category=role_category,
        remote_type=remote_type,
        seniority_level=seniority_level,
        is_non_technical=is_non_technical,
        description_text=description_text,
        apply_url=apply_url,
        canonical_url=canonical_url,
        content_hash=content_hash,
        dedupe_key=dedupe_key,
        duplicate_of_job_id=duplicate_of_job_id,
        posted_at=raw.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
        raw_payload=raw.raw_payload,
    )
    db.add(job)
    db.flush()
    _replace_locations(db, job, raw.locations)
    return job, True


def _run_source(db: Session, job_source: JobSource, now: datetime) -> tuple[DiscoveryRunSource, int]:
    settings = get_settings()
    adapter = get_adapter(job_source.provider)
    run_source = DiscoveryRunSource(job_source_id=job_source.id, started_at=now)

    try:
        raw_jobs = adapter(
            job_source.board_token,
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
            min_request_interval_seconds=settings.http_min_request_interval_seconds,
        )
    except JobSourceFetchError as exc:
        job_source.last_fetch_status = FetchStatus.FAILURE
        job_source.last_fetch_error = str(exc)
        job_source.last_fetched_at = now
        run_source.status = FetchStatus.FAILURE
        run_source.error_message = str(exc)
        run_source.finished_at = datetime.now(timezone.utc)
        logger.warning(
            "discovery_source_failed",
            extra=log_extra(job_source_id=job_source.id, provider=job_source.provider.value, error=str(exc)),
        )
        return run_source, 0

    jobs_created = 0
    jobs_updated = 0
    seen_external_ids: set[str] = set()
    for raw in raw_jobs:
        seen_external_ids.add(raw.external_id)
        _, created = _upsert_job(db, job_source, job_source.employer.name, raw, now)
        if created:
            jobs_created += 1
        else:
            jobs_updated += 1

    jobs_deactivated = 0
    active_jobs = db.execute(
        select(Job).where(Job.job_source_id == job_source.id, Job.is_active.is_(True))
    ).scalars().all()
    for job in active_jobs:
        if job.external_id not in seen_external_ids:
            job.is_active = False
            jobs_deactivated += 1

    job_source.last_fetch_status = FetchStatus.SUCCESS
    job_source.last_fetch_error = None
    job_source.last_fetched_at = now

    run_source.status = FetchStatus.SUCCESS
    run_source.jobs_found = len(raw_jobs)
    run_source.jobs_created = jobs_created
    run_source.jobs_updated = jobs_updated
    run_source.finished_at = datetime.now(timezone.utc)

    logger.info(
        "discovery_source_succeeded",
        extra=log_extra(
            job_source_id=job_source.id,
            provider=job_source.provider.value,
            jobs_found=len(raw_jobs),
            jobs_created=jobs_created,
            jobs_updated=jobs_updated,
            jobs_deactivated=jobs_deactivated,
        ),
    )
    return run_source, jobs_deactivated


def is_discovery_running(db: Session) -> bool:
    return (
        db.execute(select(DiscoveryRun.id).where(DiscoveryRun.status == RunStatus.RUNNING)).scalars().first()
        is not None
    )


def run_discovery(db: Session, trigger_type: TriggerType) -> DiscoveryRun:
    if is_discovery_running(db):
        raise ConflictError("A discovery run is already in progress")

    started_at = datetime.now(timezone.utc)
    run = DiscoveryRun(trigger_type=trigger_type, status=RunStatus.RUNNING, started_at=started_at)
    db.add(run)
    db.commit()
    db.refresh(run)

    job_sources = list(
        db.execute(
            select(JobSource).options(joinedload(JobSource.employer)).where(JobSource.is_enabled.is_(True))
        ).scalars()
    )

    sources_succeeded = 0
    total_created = 0
    total_updated = 0
    total_deactivated = 0

    for job_source in job_sources:
        step_now = datetime.now(timezone.utc)
        run_source, deactivated = _run_source(db, job_source, step_now)
        run_source.discovery_run_id = run.id
        db.add(run_source)
        db.commit()

        if run_source.status == FetchStatus.SUCCESS:
            sources_succeeded += 1
        total_created += run_source.jobs_created
        total_updated += run_source.jobs_updated
        total_deactivated += deactivated

    run.finished_at = datetime.now(timezone.utc)
    run.sources_attempted = len(job_sources)
    run.sources_succeeded = sources_succeeded
    run.jobs_created = total_created
    run.jobs_updated = total_updated
    run.jobs_deactivated = total_deactivated

    if not job_sources or sources_succeeded == len(job_sources):
        run.status = RunStatus.SUCCEEDED
    elif sources_succeeded == 0:
        run.status = RunStatus.FAILED
        run.error_summary = "All enabled job sources failed to fetch. See per-source errors."
    else:
        run.status = RunStatus.PARTIAL

    db.commit()
    db.refresh(run)

    logger.info(
        "discovery_run_finished",
        extra=log_extra(
            run_id=run.id,
            status=run.status.value,
            sources_attempted=run.sources_attempted,
            sources_succeeded=run.sources_succeeded,
            jobs_created=run.jobs_created,
            jobs_updated=run.jobs_updated,
            jobs_deactivated=run.jobs_deactivated,
        ),
    )
    return run


def list_discovery_runs(db: Session, limit: int = 10) -> list[DiscoveryRun]:
    return list(
        db.execute(
            select(DiscoveryRun)
            .options(joinedload(DiscoveryRun.sources).joinedload(DiscoveryRunSource.job_source).joinedload(JobSource.employer))
            .order_by(DiscoveryRun.started_at.desc())
            .limit(limit)
        )
        .unique()
        .scalars()
    )


def get_latest_discovery_run(db: Session) -> DiscoveryRun | None:
    runs = list_discovery_runs(db, limit=1)
    return runs[0] if runs else None
