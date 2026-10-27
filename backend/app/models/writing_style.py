"""Writing style profile (Phase 2.2.1).

One editable preference row per candidate. Writing samples live in a
separate table so stylistic text is never mixed with qualifications.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, pg_enum
from app.models.enums import (
    WritingComplexity,
    WritingFormality,
    WritingLength,
    WritingTechnicalDetail,
    WritingTone,
    WritingVocabulary,
)


class WritingStyleProfile(TimestampMixin, Base):
    __tablename__ = "writing_style_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    tone: Mapped[WritingTone] = mapped_column(
        pg_enum(WritingTone, "writing_tone_enum"),
        nullable=False,
        default=WritingTone.PROFESSIONAL_CONVERSATIONAL,
        server_default=WritingTone.PROFESSIONAL_CONVERSATIONAL.value,
    )
    formality: Mapped[WritingFormality] = mapped_column(
        pg_enum(WritingFormality, "writing_formality_enum"),
        nullable=False,
        default=WritingFormality.MEDIUM,
        server_default=WritingFormality.MEDIUM.value,
    )
    preferred_length: Mapped[WritingLength] = mapped_column(
        pg_enum(WritingLength, "writing_length_enum"),
        nullable=False,
        default=WritingLength.SHORT_MEDIUM,
        server_default=WritingLength.SHORT_MEDIUM.value,
    )
    sentence_complexity: Mapped[WritingComplexity] = mapped_column(
        pg_enum(WritingComplexity, "writing_complexity_enum"),
        nullable=False,
        default=WritingComplexity.MODERATE,
        server_default=WritingComplexity.MODERATE.value,
    )
    technical_detail: Mapped[WritingTechnicalDetail] = mapped_column(
        pg_enum(WritingTechnicalDetail, "writing_technical_detail_enum"),
        nullable=False,
        default=WritingTechnicalDetail.SPECIFIC,
        server_default=WritingTechnicalDetail.SPECIFIC.value,
    )
    vocabulary: Mapped[WritingVocabulary] = mapped_column(
        pg_enum(WritingVocabulary, "writing_vocabulary_enum"),
        nullable=False,
        default=WritingVocabulary.STRAIGHTFORWARD,
        server_default=WritingVocabulary.STRAIGHTFORWARD.value,
    )
    phrases_to_avoid: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    additional_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    __table_args__ = (UniqueConstraint("candidate_id", name="uq_writing_style_profiles_candidate"),)
