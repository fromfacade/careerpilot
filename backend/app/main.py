from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.applications import router as applications_router
from app.api.auto_apply import router as auto_apply_router
from app.api.autofill import router as autofill_router
from app.api.candidate import router as candidate_router
from app.api.ai import router as ai_router
from app.api.answers import router as answers_router
from app.api.canonical import router as canonical_router
from app.api.discovery import router as discovery_router
from app.api.health import router as health_router
from app.api.job_sources import router as job_sources_router
from app.api.jobs import router as jobs_router
from app.api.preparations import router as preparations_router
from app.api.resumes import facts_router, resumes_router
from app.api.writing_samples import router as writing_samples_router
from app.api.writing_style import router as writing_style_router
from app.core.config import get_settings
from app.core.local_guard import LocalRequestGuard
from app.core.logging import configure_logging, get_logger
from app.scheduling.scheduler import start_scheduler, stop_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("careerpilot_api_startup", extra={"extra_fields": {"version": app.version}})
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("careerpilot_api_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="CareerPilot API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it runs first and can refuse a foreign site before any route loads candidate data.
    app.add_middleware(LocalRequestGuard)

    app.include_router(health_router)
    app.include_router(candidate_router)
    app.include_router(auto_apply_router)
    app.include_router(job_sources_router)
    app.include_router(jobs_router)
    app.include_router(discovery_router)
    app.include_router(resumes_router)
    app.include_router(facts_router)
    app.include_router(canonical_router)
    app.include_router(answers_router)
    app.include_router(writing_style_router)
    app.include_router(writing_samples_router)
    app.include_router(preparations_router)
    app.include_router(applications_router)
    app.include_router(autofill_router)
    app.include_router(ai_router)

    return app


app = create_app()
