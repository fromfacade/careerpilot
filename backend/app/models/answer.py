"""Reusable application answer library (Phase 2.2).

Answers are independent of any resume. They may link to canonical facts
as supporting evidence; deleting a canonical fact SET NULLs the link, it
does not delete the answer. Sensitive categories never become `approved`
in one step from `draft` — they must pass through `reviewed`.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import AnswerCategory, AnswerOrigin, AnswerStatus


class ApplicationAnswer(TimestampMixin, Base):
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[AnswerCategory] = mapped_column(
        pg_enum(AnswerCategory, "answer_category_enum"),
        nullable=False,
        default=AnswerCategory.OTHER,
        server_default=AnswerCategory.OTHER.value,
    )
    status: Mapped[AnswerStatus] = mapped_column(
        pg_enum(AnswerStatus, "answer_status_enum"),
        nullable=False,
        default=AnswerStatus.DRAFT,
        server_default=AnswerStatus.DRAFT.value,
    )
    origin: Mapped[AnswerOrigin] = mapped_column(
        pg_enum(AnswerOrigin, "answer_origin_enum"),
        nullable=False,
        default=AnswerOrigin.MANUAL,
        server_default=AnswerOrigin.MANUAL.value,
    )
    is_reusable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    prefer_not_to_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    missing_information: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    generation_metadata: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict
    )
    rewritten_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_answers.id", ondelete="SET NULL"), nullable=True
    )
    unsupported_claims: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )

    fact_links: Mapped[list["ApplicationAnswerFact"]] = relationship(
        back_populates="answer", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_application_answers_candidate_category", "candidate_id", "category"),
        Index("ix_application_answers_fingerprint", "candidate_id", "question_fingerprint"),
        Index(
            "uq_application_answers_preferred_per_question",
            "candidate_id",
            "question_fingerprint",
            unique=True,
            postgresql_where=text("is_preferred IS TRUE"),
        ),
        UniqueConstraint(
            "candidate_id",
            "question_fingerprint",
            "answer_text",
            name="uq_application_answers_equivalent",
        ),
    )


class ApplicationAnswerFact(TimestampMixin, Base):
    """Join: which canonical facts grounded this answer."""

    __tablename__ = "application_answer_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("application_answers.id", ondelete="CASCADE"), nullable=False
    )
    canonical_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_facts.id", ondelete="SET NULL"), nullable=True
    )

    answer: Mapped[ApplicationAnswer] = relationship(back_populates="fact_links")

    __table_args__ = (
        UniqueConstraint("answer_id", "canonical_fact_id", name="uq_answer_fact_link"),
    )
