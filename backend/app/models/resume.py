"""Resume uploads and the verified candidate fact vault (Phase 2.1).

`Resume` rows are write-once: nothing in this codebase ever updates
`original_filename`/`storage_path`/`sha256_checksum`/`file_size_bytes`/
`file_format` after creation, and there is no PATCH/PUT/DELETE endpoint for
a resume at all (see app/api/resumes.py). `parse_status`/`parse_error` are
the one exception -- set exactly once, synchronously, during the upload
request itself.

`CandidateFact` rows are the generalized fact vault sketched (but not
migrated) in docs/data-model.md Phase 1. Facts extracted from a resume
start life as `verification_status=UNVERIFIED`; only a human action via
`PATCH /api/candidate/facts/{id}` can move them to VERIFIED/EDITED/
REJECTED. Nothing in this module ever marks a fact VERIFIED on its own.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import FactSource, FactType, FactVerificationStatus, ResumeFileFormat, ResumeParseStatus


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

    facts: Mapped[list["CandidateFact"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class CandidateFact(TimestampMixin, Base):
    __tablename__ = "candidate_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
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
