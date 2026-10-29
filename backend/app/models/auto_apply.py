"""One Auto-Apply grant per candidate.

Discovery preferences stay on `candidate_preferences`. This row is the only
place a user opts in to a future automatic submission. It stores no browser
credentials and no application answers.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import EmploymentType, RoleCategory


class AutoApplyAuthorization(TimestampMixin, Base):
    __tablename__ = "auto_apply_authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_categories: Mapped[list[RoleCategory]] = mapped_column(
        ARRAY(pg_enum(RoleCategory, "role_category_enum")),
        nullable=False,
        default=list,
        server_default="{}",
    )
    employment_types: Mapped[list[EmploymentType]] = mapped_column(
        ARRAY(pg_enum(EmploymentType, "employment_type_enum")),
        nullable=False,
        default=list,
        server_default="{}",
    )
    locations: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default="{}",
    )
    min_match_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=70, server_default="70")
    max_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    max_per_session: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    resume_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        default=list,
        server_default="{}",
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "min_match_score >= 0 AND min_match_score <= 100",
            name="ck_auto_apply_min_score",
        ),
        CheckConstraint("max_per_day >= 0 AND max_per_day <= 25", name="ck_auto_apply_daily_limit"),
        CheckConstraint("max_per_session >= 0 AND max_per_session <= 25", name="ck_auto_apply_session_limit"),
    )
