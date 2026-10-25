from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="CareerPilot API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)

    @app.on_event("startup")
    def _on_startup() -> None:
        logger.info("careerpilot_api_startup", extra={"extra_fields": {"version": app.version}})

    return app


app = create_app()
