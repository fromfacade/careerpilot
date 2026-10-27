"""Resume uploads and the verified candidate fact vault (Phase 2.1).

`Resume` file bytes are write-once: nothing updates `original_filename`/
`storage_path`/`sha256_checksum`/`file_size_bytes`/`file_format` after
creation. There is no PATCH/PUT for those fields. `parse_status`/
`parse_error` change on upload and on explicit reprocess. `is_primary`
changes only when a resume is uploaded as the first file, set as primary,
or a primary file is deleted and the user picks a replacement.

An explicit `DELETE /api/resumes/{id}` removes that file and its
resume-specific extracted records. Verified/edited facts are detached
(`resume_id` set null) unless the caller opts in to delete them too.

`CandidateFact` rows start as `verification_status=UNVERIFIED`; only a
human action via `PATCH /api/candidate/facts/{id}` can move them to
VERIFIED/EDITED/REJECTED. Nothing here marks a fact VERIFIED on its own.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import (
    FactSource,
    FactType,
    FactVerificationStatus,
    ResumeCategory,
    ResumeFileFormat,
    ResumeParseStatus,
)


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[ResumeFileFormat] = mapped_column(
        pg_enum(ResumeFileFormat, "resume_file_format_enum"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[ResumeParseStatus] = mapped_column(
        pg_enum(ResumeParseStatus, "resume_parse_status_enum"),
        nullable=False,
        default=ResumeParseStatus.PENDING,
        server_default=ResumeParseStatus.PENDING.value,
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    profile_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    profile_description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[ResumeCategory] = mapped_column(
        pg_enum(ResumeCategory, "resume_category_enum"),
        nullable=False,
        default=ResumeCategory.CUSTOM,
        server_default=ResumeCategory.CUSTOM.value,
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    focus_areas: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)

    facts: Mapped[list["CandidateFact"]] = relationship(back_populates="resume", passive_deletes=True)

    __table_args__ = (
        Index(
            "uq_resumes_one_primary_per_candidate",
            "candidate_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE"),
        ),
    )


class CandidateFact(TimestampMixin, Base):
    __tablename__ = "candidate_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    fact_type: Mapped[FactType] = mapped_column(pg_enum(FactType, "fact_type_enum"), nullable=False)
    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    fact_value: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[FactSource] = mapped_column(
        pg_enum(FactSource, "fact_source_enum"),
        nullable=False,
        default=FactSource.RESUME_EXTRACTION,
        server_default=FactSource.RESUME_EXTRACTION.value,
    )
    verification_status: Mapped[FactVerificationStatus] = mapped_column(
        pg_enum(FactVerificationStatus, "fact_verification_status_enum"),
        nullable=False,
        default=FactVerificationStatus.UNVERIFIED,
        server_default=FactVerificationStatus.UNVERIFIED.value,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resume: Mapped[Resume | None] = relationship(back_populates="facts")
