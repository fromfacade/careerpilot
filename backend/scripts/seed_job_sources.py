"""Seed a small set of real, publicly-known employer job boards into the
job source registry.

Each (employer, provider, board_token) below was verified reachable against
the real public API during development (see docs/implementation-plan.md).
This is intentionally a short, hand-picked list, not a scraped directory —
the user is expected to add/remove boards through the registry API
(`/api/job-sources`) as their search evolves; this script just gives a new
local install something real to discover on first run.

Usage (from backend/, with the venv activated):
    python -m scripts.seed_job_sources
"""

from __future__ import annotations

from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.models.enums import JobProvider
from app.schemas.job_source import JobSourceCreate
from app.services import job_source_service
from app.core.exceptions import ConflictError

logger = get_logger(__name__)

SEED_SOURCES: list[JobSourceCreate] = [
    JobSourceCreate(employer_name="Stripe", provider=JobProvider.GREENHOUSE, board_token="stripe"),
    JobSourceCreate(employer_name="Palantir", provider=JobProvider.LEVER, board_token="palantir"),
    JobSourceCreate(employer_name="OpenAI", provider=JobProvider.ASHBY, board_token="openai"),
    JobSourceCreate(employer_name="Notion", provider=JobProvider.ASHBY, board_token="notion"),
    JobSourceCreate(employer_name="Ramp", provider=JobProvider.ASHBY, board_token="ramp"),
]


def main() -> None:
    configure_logging("INFO")
    created = 0
    skipped = 0
    with session_scope() as db:
        for seed in SEED_SOURCES:
            try:
                job_source_service.create_job_source(db, seed)
                created += 1
                print(f"created: {seed.provider.value}/{seed.board_token} ({seed.employer_name})")
            except ConflictError:
                skipped += 1
                print(f"already exists, skipped: {seed.provider.value}/{seed.board_token}")

    print(f"\nDone. created={created} skipped={skipped}")


if __name__ == "__main__":
    main()
