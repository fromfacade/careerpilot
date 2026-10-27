"""Persistent application tracking (Phase 2.5.2).

One row per candidate and job. It records status only. It does not store
answers, credentials, or the application form.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import ApplicationStatus


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

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_tracked_application_candidate_job"),
    )
