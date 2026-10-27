"""Canonical candidate knowledge base (Phase 2.2).

`CanonicalFact` is the authoritative version of one piece of information
about the candidate. It does **not** belong to a resume: there is no
required `resume_id`, and deleting an uploaded resume never cascades here.

Extracted `candidate_facts` stay as they are (traceability). Promoting a
verified extracted record creates or links a canonical row and records the
link in `CanonicalFactSource`. Conflicts (same identity, different content)
become a second row with `status=conflict` instead of overwriting.

Nothing in this module marks a fact verified on its own.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import (
    CanonicalFactOrigin,
    CanonicalFactStatus,
    FactType,
    FactVerificationStatus,
)


class CanonicalFact(TimestampMixin, Base):
    __tablename__ = "canonical_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    fact_type: Mapped[FactType] = mapped_column(pg_enum(FactType, "fact_type_enum"), nullable=False)
    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    fact_value: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    # `type|normalized_key` — one *active* row per identity per candidate.
    identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Exact-content fingerprint (review metadata stripped). Used to skip
    # re-importing a fact the knowledge base already holds.
    content_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CanonicalFactStatus] = mapped_column(
        pg_enum(CanonicalFactStatus, "canonical_fact_status_enum"),
        nullable=False,
        default=CanonicalFactStatus.ACTIVE,
        server_default=CanonicalFactStatus.ACTIVE.value,
    )
    verification_status: Mapped[FactVerificationStatus] = mapped_column(
        pg_enum(FactVerificationStatus, "fact_verification_status_enum"),
        nullable=False,
        default=FactVerificationStatus.UNVERIFIED,
        server_default=FactVerificationStatus.UNVERIFIED.value,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    review_reasons: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    conflicts_with_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_facts.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sources: Mapped[list["CanonicalFactSource"]] = relationship(
        back_populates="canonical_fact", cascade="all, delete-orphan", passive_deletes=True
    )
    conflicts_with: Mapped["CanonicalFact | None"] = relationship(
        remote_side="CanonicalFact.id", foreign_keys=[conflicts_with_id]
    )

    __table_args__ = (
        Index(
            "uq_canonical_facts_active_identity",
            "candidate_id",
            "identity_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_canonical_facts_candidate_status", "candidate_id", "status"),
        Index("ix_canonical_facts_fingerprint", "candidate_id", "content_fingerprint"),
    )


class CanonicalFactSource(TimestampMixin, Base):
    """Provenance for one canonical fact: which extracted record, resume,
    or user action supplied it. Survives resume deletion (`resume_id` and
    `candidate_fact_id` SET NULL); the canonical row itself is untouched.
    """

    __tablename__ = "canonical_fact_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_fact_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_facts.id", ondelete="CASCADE"), nullable=False
    )
    candidate_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_facts.id", ondelete="SET NULL"), nullable=True
    )
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    origin: Mapped[CanonicalFactOrigin] = mapped_column(
        pg_enum(CanonicalFactOrigin, "canonical_fact_origin_enum"),
        nullable=False,
        default=CanonicalFactOrigin.MANUAL_ENTRY,
        server_default=CanonicalFactOrigin.MANUAL_ENTRY.value,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    canonical_fact: Mapped[CanonicalFact] = relationship(back_populates="sources")

    __table_args__ = (
        Index(
            "uq_canonical_source_extracted_fact",
            "candidate_fact_id",
            unique=True,
            postgresql_where=text("candidate_fact_id IS NOT NULL"),
        ),
    )
