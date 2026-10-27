"""application preparations

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-26

Job-specific application prep. Not a submission queue.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    state = postgresql.ENUM(
        "preparing",
        "needs_review",
        "ready",
        "failed",
        "cancelled",
        name="preparation_state_enum",
    )
    item_status = postgresql.ENUM(
        "draft",
        "approved",
        "rejected",
        "needs_review",
        name="preparation_item_status_enum",
    )
    answer_origin = postgresql.ENUM(
        "reused",
        "adapted",
        "generated",
        name="preparation_answer_origin_enum",
    )
    state.create(op.get_bind(), checkfirst=True)
    item_status.create(op.get_bind(), checkfirst=True)
    answer_origin.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "application_preparations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("source_resume_id", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            postgresql.ENUM(name="preparation_state_enum", create_type=False),
            server_default="preparing",
            nullable=False,
        ),
        sa.Column("snapshot_job_title", sa.Text(), nullable=False),
        sa.Column("snapshot_employer", sa.Text(), nullable=False),
        sa.Column("snapshot_description", sa.Text(), server_default="", nullable=False),
        sa.Column("snapshot_apply_url", sa.Text(), server_default="", nullable=False),
        sa.Column("snapshot_content_hash", sa.Text(), server_default="", nullable=False),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("match_report", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("tailored_resume", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "tailored_resume_status",
            postgresql.ENUM(name="preparation_item_status_enum", create_type=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("design_limitation", sa.Text(), server_default="", nullable=False),
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
        sa.Column("docx_path", sa.Text(), nullable=True),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_preparations_candidate_job",
        "application_preparations",
        ["candidate_id", "job_id"],
    )
    op.create_index(
        "uq_application_preparations_open",
        "application_preparations",
        ["candidate_id", "job_id"],
        unique=True,
        postgresql_where=sa.text(
            "state IN ('preparing', 'needs_review', 'ready', 'failed') AND job_id IS NOT NULL"
        ),
    )

    op.create_table(
        "application_preparation_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preparation_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(name="answer_category_enum", create_type=False),
            server_default="other",
            nullable=False,
        ),
        sa.Column(
            "origin",
            postgresql.ENUM(name="preparation_answer_origin_enum", create_type=False),
            server_default="generated",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="preparation_item_status_enum", create_type=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("source_answer_id", sa.Integer(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("canonical_fact_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("unsupported_claims", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("missing_information", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["preparation_id"], ["application_preparations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_answer_id"], ["application_answers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preparation_id", "question", name="uq_preparation_answer_question"),
    )


def downgrade() -> None:
    op.drop_table("application_preparation_answers")
    op.drop_index("uq_application_preparations_open", table_name="application_preparations")
    op.drop_index("ix_application_preparations_candidate_job", table_name="application_preparations")
    op.drop_table("application_preparations")
    postgresql.ENUM(name="preparation_answer_origin_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="preparation_item_status_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="preparation_state_enum").drop(op.get_bind(), checkfirst=True)
