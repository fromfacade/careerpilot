"""One-time backfill for `Job.seniority_level` / `Job.is_non_technical`.

These two fields were added after jobs had already been discovered and
persisted (see `alembic/versions/f0bf71529485_*`). Discovery only
recomputes them for a given job when its `content_hash` changes (i.e. the
posting's title/description/locations actually changed), so every job
discovered *before* that migration needs a one-time pass to get classified
-- otherwise Priority 3's relevance fix (not_relevant capping, "do not
equate an irrelevant role with eligibility failure") silently does nothing
for the ~2000+ jobs already in the dev database.

This also recomputes every candidate's assessments afterward, since
`relevance`/`match_score` depend on the now-correct `seniority_level` /
`is_non_technical` values.

Usage (from backend/, with the venv activated):
    python -m scripts.backfill_job_classification
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.models.candidate import Candidate
from app.models.job import Job
from app.sources import normalize
from app.services import job_service

logger = get_logger(__name__)


def main() -> None:
    configure_logging("INFO")

    jobs_updated = 0
    with session_scope() as db:
        jobs = db.execute(select(Job)).scalars().all()
        for job in jobs:
            seniority_level = normalize.infer_seniority_level(job.title)
            is_non_technical = normalize.infer_is_non_technical(job.title)
            if job.seniority_level != seniority_level or job.is_non_technical != is_non_technical:
                job.seniority_level = seniority_level
                job.is_non_technical = is_non_technical
                jobs_updated += 1
        print(f"Reclassified {jobs_updated} / {len(jobs)} job(s) (seniority_level / is_non_technical).")

        candidates = db.execute(select(Candidate)).scalars().all()
        for candidate in candidates:
            count = job_service.recompute_all_assessments(db, candidate)
            print(f"Recomputed {count} assessment(s) for candidate #{candidate.id} ({candidate.email}).")

    print("\nDone.")


if __name__ == "__main__":
    main()
