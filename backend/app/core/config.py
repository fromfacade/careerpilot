"""Application settings, loaded from environment variables / .env.

Centralizing settings here means no other module reads os.environ directly,
which keeps configuration testable (tests can construct a Settings object
with explicit overrides) and avoids scattering magic env var names.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg://careerpilot:careerpilot_dev_password@127.0.0.1:5432/careerpilot_dev",
        description="SQLAlchemy connection string for the primary application database.",
    )
    test_database_url: str = Field(
        default="postgresql+psycopg://careerpilot:careerpilot_dev_password@127.0.0.1:5432/careerpilot_test",
        description="SQLAlchemy connection string used by the automated test suite.",
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")

    # --- CORS ---
    cors_allowed_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    # --- Outbound HTTP (job source adapters) ---
    http_timeout_seconds: float = Field(default=10.0)
    http_max_retries: int = Field(default=3)
    http_min_request_interval_seconds: float = Field(default=0.5)

    # --- Scheduler ---
    discovery_scheduler_enabled: bool = Field(default=True)
    discovery_interval_minutes: int = Field(default=180)

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Tests override via dependency_overrides / direct construction."""
    return Settings()
