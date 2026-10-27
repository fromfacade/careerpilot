"""Job-specific application preparation (Phase 2.3).

A preparation is review material for one job. It is not a submission.
Original resume bytes are never stored here or modified; tailored artifacts
are written under storage/preparations/.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import (
    AnswerCategory,
    PreparationAnswerOrigin,
    PreparationItemStatus,
    PreparationState,
)


class ApplicationPreparation(TimestampMixin, Base):
    __tablename__ = "application_preparations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    source_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[PreparationState] = mapped_column(
        pg_enum(PreparationState, "preparation_state_enum"),
        nullable=False,
        default=PreparationState.PREPARING,
        server_default=PreparationState.PREPARING.value,
    )
    snapshot_job_title: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_employer: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    snapshot_apply_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    snapshot_content_hash: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    analysis: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    match_report: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    tailored_resume: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    tailored_resume_status: Mapped[PreparationItemStatus] = mapped_column(
        pg_enum(PreparationItemStatus, "preparation_item_status_enum"),
        nullable=False,
        default=PreparationItemStatus.DRAFT,
        server_default=PreparationItemStatus.DRAFT.value,
    )
    design_limitation: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    answers: Mapped[list["ApplicationPreparationAnswer"]] = relationship(
        back_populates="preparation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_application_preparations_candidate_job", "candidate_id", "job_id"),
        Index(
            "uq_application_preparations_open",
            "candidate_id",
            "job_id",
            unique=True,
            postgresql_where=text(
                "state IN ('preparing', 'needs_review', 'ready', 'failed') AND job_id IS NOT NULL"
            ),
        ),
    )


class ApplicationPreparationAnswer(TimestampMixin, Base):
    __tablename__ = "application_preparation_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    preparation_id: Mapped[int] = mapped_column(
        ForeignKey("application_preparations.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[AnswerCategory] = mapped_column(
        pg_enum(AnswerCategory, "answer_category_enum"),
        nullable=False,
        default=AnswerCategory.OTHER,
        server_default=AnswerCategory.OTHER.value,
    )
    origin: Mapped[PreparationAnswerOrigin] = mapped_column(
        pg_enum(PreparationAnswerOrigin, "preparation_answer_origin_enum"),
        nullable=False,
        default=PreparationAnswerOrigin.GENERATED,
        server_default=PreparationAnswerOrigin.GENERATED.value,
    )
    status: Mapped[PreparationItemStatus] = mapped_column(
        pg_enum(PreparationItemStatus, "preparation_item_status_enum"),
        nullable=False,
        default=PreparationItemStatus.DRAFT,
        server_default=PreparationItemStatus.DRAFT.value,
    )
    source_answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_answers.id", ondelete="SET NULL"), nullable=True
    )
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    canonical_fact_ids: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    unsupported_claims: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    missing_information: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )

    preparation: Mapped[ApplicationPreparation] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("preparation_id", "question", name="uq_preparation_answer_question"),
    )
