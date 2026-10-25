"""Shared model mixins."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Native Postgres enum column backed by a Python str-Enum's `.value`s.

    SQLAlchemy's default `Enum` stores the Python member *name* (e.g.
    "UNKNOWN") in the database, not `.value` ("unknown"). We always want the
    lowercase `.value` stored (it's what `docs/data-model.md` documents and
    what `server_default` strings below are written against), so every enum
    column in this app must be created via this helper instead of calling
    `Enum(...)` directly.
    """
    return SAEnum(enum_cls, name=name, native_enum=True, values_callable=lambda obj: [e.value for e in obj])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
