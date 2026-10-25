from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure `app` is importable regardless of the working directory alembic is
# invoked from (prepend_sys_path = . in alembic.ini already adds backend/,
# which is where this is run from per the README instructions).
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers all models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Single source of truth for the DB URL: app.core.config.Settings, which
# reads backend/.env. This avoids keeping a second, driftable URL in
# alembic.ini -- BUT callers (e.g. tests/conftest.py's `test_engine`
# fixture, which needs migrations applied to `careerpilot_test`, not dev)
# are allowed to set `sqlalchemy.url` on the Config object before invoking
# Alembic, and that explicit choice must win. `alembic.ini` deliberately
# leaves `sqlalchemy.url` unset (see comment there), so "already set" only
# ever means a caller set it on purpose.
#
# This used to unconditionally overwrite whatever the caller set, which
# silently defeated conftest.py's attempt to migrate the test database --
# the test suite happened to pass anyway only because the dev and test
# schemas were kept in sync by hand. Fixed here.
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
