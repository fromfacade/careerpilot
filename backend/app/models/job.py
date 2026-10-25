from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import Eligibility, EmploymentType, JobState, RemoteType, RoleCategory


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_source_id: Mapped[int] = mapped_column(ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[EmploymentType] = mapped_column(
        pg_enum(EmploymentType, "employment_type_enum"),
        nullable=False,
        default=EmploymentType.UNKNOWN,
        server_default=EmploymentType.UNKNOWN.value,
    )
    role_category: Mapped[RoleCategory] = mapped_column(
        pg_enum(RoleCategory, "role_category_enum"),
        nullable=False,
        default=RoleCategory.OTHER,
        server_default=RoleCategory.OTHER.value,
    )
    remote_type: Mapped[RemoteType] = mapped_column(
        pg_enum(RemoteType, "remote_type_enum"),
        nullable=False,
        default=RemoteType.UNKNOWN,
        server_default=RemoteType.UNKNOWN.value,
    )
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    duplicate_of_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)

    job_source: Mapped["JobSource"] = relationship(back_populates="jobs")
    locations: Mapped[list["JobLocation"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    candidate_states: Mapped[list["JobCandidateState"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    assessments: Mapped[list["JobAssessment"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("job_source_id", "external_id", name="uq_job_source_external_id"),
    )


class JobLocation(Base):
    __tablename__ = "job_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    job: Mapped[Job] = relationship(back_populates="locations")

    __table_args__ = (UniqueConstraint("job_id", "raw_text", name="uq_job_location_raw_text"),)


class JobCandidateState(TimestampMixin, Base):
    __tablename__ = "job_candidate_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[JobState] = mapped_column(
        pg_enum(JobState, "job_state_enum"),
        nullable=False,
        default=JobState.NEW,
        server_default=JobState.NEW.value,
    )
    state_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="candidate_states")

    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_job_candidate_state"),)


class JobAssessment(Base):
    __tablename__ = "job_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    eligibility: Mapped[Eligibility] = mapped_column(
        pg_enum(Eligibility, "eligibility_enum"),
        nullable=False,
        default=Eligibility.UNKNOWN,
        server_default=Eligibility.UNKNOWN.value,
    )
    eligibility_reasons: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    match_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    match_reasons: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped[Job] = relationship(back_populates="assessments")

    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_job_assessment"),
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_job_assessment_score_range"),
    )
