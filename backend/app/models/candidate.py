from __future__ import annotations

from datetime import date

from sqlalchemy import ARRAY, CheckConstraint, Date, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import DatePrecision, DegreeLevel, EmploymentType, LocationPreferenceType, RoleCategory, TriState, WorkAuthStatus


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    school: Mapped[str | None] = mapped_column(Text, nullable=True)
    degree_level: Mapped[DegreeLevel] = mapped_column(
        pg_enum(DegreeLevel, "degree_level_enum"),
        nullable=False,
        default=DegreeLevel.UNKNOWN,
        server_default=DegreeLevel.UNKNOWN.value,
    )
    major: Mapped[str | None] = mapped_column(Text, nullable=True)
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    graduation_date_precision: Mapped[DatePrecision] = mapped_column(
        pg_enum(DatePrecision, "date_precision_enum"),
        nullable=False,
        default=DatePrecision.UNKNOWN,
        server_default=DatePrecision.UNKNOWN.value,
    )
    work_authorization_status: Mapped[WorkAuthStatus] = mapped_column(
        pg_enum(WorkAuthStatus, "work_auth_status_enum"),
        nullable=False,
        default=WorkAuthStatus.UNKNOWN,
        server_default=WorkAuthStatus.UNKNOWN.value,
    )
    requires_sponsorship: Mapped[TriState] = mapped_column(
        pg_enum(TriState, "tri_state_enum"),
        nullable=False,
        default=TriState.UNKNOWN,
        server_default=TriState.UNKNOWN.value,
    )
    current_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_resume_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    preferences: Mapped["CandidatePreference | None"] = relationship(
        back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )
    location_preferences: Mapped[list["CandidateLocationPreference"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateLocationPreference.priority"
    )
    role_preferences: Mapped[list["CandidateRolePreference"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateRolePreference.priority"
    )


class CandidatePreference(TimestampMixin, Base):
    __tablename__ = "candidate_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    remote_ok: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    target_employment_types: Mapped[list[EmploymentType]] = mapped_column(
        ARRAY(pg_enum(EmploymentType, "employment_type_enum")),
        nullable=False,
        default=list,
        server_default="{}",
    )
    target_start_window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_start_window_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    min_match_score_to_surface: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )

    candidate: Mapped[Candidate] = relationship(back_populates="preferences")

    __table_args__ = (
        CheckConstraint(
            "min_match_score_to_surface >= 0 AND min_match_score_to_surface <= 100",
            name="ck_candidate_preferences_min_score_range",
        ),
    )


class CandidateLocationPreference(Base):
    __tablename__ = "candidate_location_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    location_type: Mapped[LocationPreferenceType] = mapped_column(
        pg_enum(LocationPreferenceType, "location_pref_type_enum"), nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    candidate: Mapped[Candidate] = relationship(back_populates="location_preferences")

    __table_args__ = (UniqueConstraint("candidate_id", "label", name="uq_candidate_location_pref"),)


class CandidateRolePreference(Base):
    __tablename__ = "candidate_role_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    role_category: Mapped[RoleCategory] = mapped_column(
        pg_enum(RoleCategory, "role_category_enum"), nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    candidate: Mapped[Candidate] = relationship(back_populates="role_preferences")

    __table_args__ = (UniqueConstraint("candidate_id", "role_category", name="uq_candidate_role_pref"),)
