"""Shared pytest fixtures.

Integration tests run against the real `careerpilot_test` PostgreSQL
database (never an in-memory substitute) with real Alembic migrations
applied once per test session. Each test runs inside an outer transaction
that is rolled back afterward, so tests never see each other's data and the
test database stays empty between runs — see the SQLAlchemy "joining a
session into an external transaction" pattern.
"""

from __future__ import annotations

import os

# Must happen before any `app.*` module is imported: app.core.config.get_settings()
# is process-wide cached, and we never want the periodic APScheduler job
# running against the real engine during a test session (it would bypass the
# per-test transaction rollback and could fire against real credentials).
os.environ.setdefault("DISCOVERY_SCHEDULER_ENABLED", "false")

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import get_db
from app.main import app as fastapi_app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def test_engine(test_settings: Settings):
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_settings.test_database_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_settings.test_database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    outer_transaction = connection.begin()

    session_factory = sessionmaker(bind=connection, future=True)
    session: Session = session_factory()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session):
    def _get_test_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _get_test_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.pop(get_db, None)
