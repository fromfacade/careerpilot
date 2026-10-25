from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import pg_enum
from app.models.enums import FetchStatus, RunStatus, TriggerType


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_type: Mapped[TriggerType] = mapped_column(
        pg_enum(TriggerType, "trigger_type_enum"), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status_enum"),
        nullable=False,
        default=RunStatus.PENDING,
        server_default=RunStatus.PENDING.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sources_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sources_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_deactivated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources: Mapped[list["DiscoveryRunSource"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class DiscoveryRunSource(Base):
    __tablename__ = "discovery_run_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=False)
    job_source_id: Mapped[int] = mapped_column(ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[FetchStatus] = mapped_column(
        pg_enum(FetchStatus, "fetch_status_enum"),
        nullable=False,
        default=FetchStatus.NEVER_RUN,
        server_default=FetchStatus.NEVER_RUN.value,
    )
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[DiscoveryRun] = relationship(back_populates="sources")
    job_source: Mapped["JobSource"] = relationship(back_populates="discovery_run_sources")

    __table_args__ = (UniqueConstraint("discovery_run_id", "job_source_id", name="uq_discovery_run_source"),)
