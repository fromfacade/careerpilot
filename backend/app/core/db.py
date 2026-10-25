"""SQLAlchemy engine/session wiring.

Business logic and API routers depend on `get_db` (a FastAPI dependency) or
`session_scope` (a plain context manager for scripts/scheduler jobs) — never
on `engine` directly — so tests can swap in a different database URL cleanly.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def build_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


_settings = get_settings()
engine = build_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope(session_factory: sessionmaker = SessionLocal) -> Generator[Session, None, None]:
    """Context manager for non-request code paths (scheduler jobs, scripts)."""
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
