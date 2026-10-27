"""tracked application records

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-10-27

One status row per candidate and job. No answers or credentials are stored.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "i9d0e1f2a3b4"
down_revision: Union[str, None] = "h8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "preparing",
        "needs_review",
        "ready_to_submit",
        "submitting",
        "submitted",
        "submission_failed",
        "confirmation_unknown",
        name="application_status_enum",
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "tracked_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("employer", sa.Text(), nullable=False),
        sa.Column("preparation_id", sa.Integer(), nullable=True),
        sa.Column("resume_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="application_status_enum", create_type=False),
            server_default="preparing",
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["preparation_id"], ["application_preparations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_tracked_application_candidate_job"),
    )


def downgrade() -> None:
    op.drop_table("tracked_applications")
    postgresql.ENUM(name="application_status_enum").drop(op.get_bind(), checkfirst=True)
