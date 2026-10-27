"""writing samples

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-26

Stylistic examples stored separately from qualifications. Deleting an
answer SET NULLs source_answer_id; the sample remains.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    category = postgresql.ENUM(
        "technical_experience",
        "motivation",
        "general",
        "other",
        name="writing_sample_category_enum",
    )
    origin = postgresql.ENUM(
        "user_written",
        "adopted_from_answer",
        name="writing_sample_origin_enum",
    )
    category.create(op.get_bind(), checkfirst=True)
    origin.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "writing_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(name="writing_sample_category_enum", create_type=False),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "origin",
            postgresql.ENUM(name="writing_sample_origin_enum", create_type=False),
            server_default="user_written",
            nullable=False,
        ),
        sa.Column("is_approved_style_reference", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("source_answer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_answer_id"], ["application_answers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "content_fingerprint", name="uq_writing_samples_fingerprint"),
    )
    op.create_index("ix_writing_samples_candidate_category", "writing_samples", ["candidate_id", "category"])


def downgrade() -> None:
    op.drop_index("ix_writing_samples_candidate_category", table_name="writing_samples")
    op.drop_table("writing_samples")
    postgresql.ENUM(name="writing_sample_origin_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="writing_sample_category_enum").drop(op.get_bind(), checkfirst=True)
