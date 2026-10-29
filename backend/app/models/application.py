"""Persistent application tracking (Phase 2.5.2).

One row per candidate and job. It records status only. It does not store
answers, credentials, or the application form.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import ApplicationEventSource, ApplicationStatus


class TrackedApplication(TimestampMixin, Base):
    __tablename__ = "tracked_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    employer: Mapped[str] = mapped_column(Text, nullable=False)
    preparation_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_preparations.id", ondelete="SET NULL"), nullable=True
    )
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status_enum"),
        nullable=False,
        default=ApplicationStatus.PREPARING,
        server_default=ApplicationStatus.PREPARING.value,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resubmit_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application",
        order_by="ApplicationEvent.id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_tracked_application_candidate_job"),
    )


class ApplicationEvent(Base):
    """One status change. The reason is a short redacted summary, never an answer."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status_enum"), nullable=False
    )
    new_status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status_enum"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[ApplicationEventSource] = mapped_column(
        pg_enum(ApplicationEventSource, "application_event_source_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application: Mapped[TrackedApplication] = relationship(back_populates="events")
