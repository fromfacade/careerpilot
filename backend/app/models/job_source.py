from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import FetchStatus, JobProvider


class Employer(TimestampMixin, Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    job_sources: Mapped[list["JobSource"]] = relationship(back_populates="employer", cascade="all, delete-orphan")


class JobSource(TimestampMixin, Base):
    """One employer's job board on one provider — the unit of configuration
    for the job source registry (module 2)."""

    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("employers.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[JobProvider] = mapped_column(
        pg_enum(JobProvider, "job_provider_enum"), nullable=False
    )
    board_token: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180, server_default="180")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_status: Mapped[FetchStatus] = mapped_column(
        pg_enum(FetchStatus, "fetch_status_enum"),
        nullable=False,
        default=FetchStatus.NEVER_RUN,
        server_default=FetchStatus.NEVER_RUN.value,
    )
    last_fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    employer: Mapped[Employer] = relationship(back_populates="job_sources")
    jobs: Mapped[list["Job"]] = relationship(back_populates="job_source", cascade="all, delete-orphan")
    discovery_run_sources: Mapped[list["DiscoveryRunSource"]] = relationship(
        back_populates="job_source", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("provider", "board_token", name="uq_job_source_provider_board"),)
