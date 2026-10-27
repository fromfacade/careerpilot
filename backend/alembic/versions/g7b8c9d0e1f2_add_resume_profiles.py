"""resume profile metadata on existing resume rows

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-27

Adds profile fields to `resumes` and selection fields to preparations.
Existing file bytes and extracted facts are not rewritten.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    category = postgresql.ENUM(
        "general_swe",
        "backend",
        "fullstack",
        "ai_ml",
        "custom",
        name="resume_category_enum",
    )
    category.create(op.get_bind(), checkfirst=True)
    source = postgresql.ENUM(
        "automatic",
        "manual",
        "fallback_default",
        "none",
        name="resume_selection_source_enum",
    )
    source.create(op.get_bind(), checkfirst=True)

    op.add_column("resumes", sa.Column("profile_name", sa.Text(), nullable=False, server_default=""))
    op.add_column("resumes", sa.Column("profile_description", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "resumes",
        sa.Column("category", category, nullable=False, server_default="custom"),
    )
    op.add_column("resumes", sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("resumes", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "resumes",
        sa.Column("focus_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.execute("UPDATE resumes SET profile_name = original_filename WHERE profile_name = ''")
    op.execute("UPDATE resumes SET is_approved = true WHERE is_primary IS TRUE")
    op.execute("UPDATE resumes SET category = 'general_swe' WHERE is_primary IS TRUE")

    op.add_column(
        "application_preparations",
        sa.Column("resume_selection_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "application_preparations",
        sa.Column(
            "resume_selection_source",
            source,
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("application_preparations", "resume_selection_source")
    op.drop_column("application_preparations", "resume_selection_reason")
    op.drop_column("resumes", "focus_areas")
    op.drop_column("resumes", "is_archived")
    op.drop_column("resumes", "is_approved")
    op.drop_column("resumes", "category")
    op.drop_column("resumes", "profile_description")
    op.drop_column("resumes", "profile_name")
    postgresql.ENUM(name="resume_selection_source_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="resume_category_enum").drop(op.get_bind(), checkfirst=True)
