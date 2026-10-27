"""Authentic writing samples (Phase 2.2.1).

Stored separately from canonical facts and application answers. An AI
draft never becomes a sample unless the candidate explicitly adopts it.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import WritingSampleCategory, WritingSampleOrigin


class WritingSample(TimestampMixin, Base):
    __tablename__ = "writing_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[WritingSampleCategory] = mapped_column(
        pg_enum(WritingSampleCategory, "writing_sample_category_enum"),
        nullable=False,
        default=WritingSampleCategory.GENERAL,
        server_default=WritingSampleCategory.GENERAL.value,
    )
    origin: Mapped[WritingSampleOrigin] = mapped_column(
        pg_enum(WritingSampleOrigin, "writing_sample_origin_enum"),
        nullable=False,
        default=WritingSampleOrigin.USER_WRITTEN,
        server_default=WritingSampleOrigin.USER_WRITTEN.value,
    )
    is_approved_style_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    source_answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_answers.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("candidate_id", "content_fingerprint", name="uq_writing_samples_fingerprint"),
    )
