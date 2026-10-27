"""writing style profile

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-26

One editable writing-preference row per candidate. Samples are a later
2.2.1 increment so stylistic text stays out of this table.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    writing_tone = postgresql.ENUM(
        "professional",
        "conversational",
        "formal",
        "professional_conversational",
        name="writing_tone_enum",
    )
    writing_formality = postgresql.ENUM("low", "medium", "high", name="writing_formality_enum")
    writing_length = postgresql.ENUM(
        "short", "short_medium", "medium", "long", name="writing_length_enum"
    )
    writing_complexity = postgresql.ENUM(
        "simple", "moderate", "varied", name="writing_complexity_enum"
    )
    writing_technical = postgresql.ENUM(
        "low", "moderate", "specific", "high", name="writing_technical_detail_enum"
    )
    writing_vocabulary = postgresql.ENUM(
        "straightforward", "technical", "mixed", name="writing_vocabulary_enum"
    )
    writing_tone.create(op.get_bind(), checkfirst=True)
    writing_formality.create(op.get_bind(), checkfirst=True)
    writing_length.create(op.get_bind(), checkfirst=True)
    writing_complexity.create(op.get_bind(), checkfirst=True)
    writing_technical.create(op.get_bind(), checkfirst=True)
    writing_vocabulary.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "writing_style_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column(
            "tone",
            postgresql.ENUM(name="writing_tone_enum", create_type=False),
            server_default="professional_conversational",
            nullable=False,
        ),
        sa.Column(
            "formality",
            postgresql.ENUM(name="writing_formality_enum", create_type=False),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "preferred_length",
            postgresql.ENUM(name="writing_length_enum", create_type=False),
            server_default="short_medium",
            nullable=False,
        ),
        sa.Column(
            "sentence_complexity",
            postgresql.ENUM(name="writing_complexity_enum", create_type=False),
            server_default="moderate",
            nullable=False,
        ),
        sa.Column(
            "technical_detail",
            postgresql.ENUM(name="writing_technical_detail_enum", create_type=False),
            server_default="specific",
            nullable=False,
        ),
        sa.Column(
            "vocabulary",
            postgresql.ENUM(name="writing_vocabulary_enum", create_type=False),
            server_default="straightforward",
            nullable=False,
        ),
        sa.Column(
            "phrases_to_avoid",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("additional_instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_writing_style_profiles_candidate"),
    )


def downgrade() -> None:
    op.drop_table("writing_style_profiles")
    for name in (
        "writing_vocabulary_enum",
        "writing_technical_detail_enum",
        "writing_complexity_enum",
        "writing_length_enum",
        "writing_formality_enum",
        "writing_tone_enum",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
