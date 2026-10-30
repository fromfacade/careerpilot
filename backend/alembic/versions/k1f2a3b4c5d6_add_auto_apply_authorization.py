"""auto-apply authorization

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-10-28

One opt-in grant per candidate. Disabled until the user acknowledges it.
No browser credentials are stored.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "k1f2a3b4c5d6"
down_revision: Union[str, None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    role = postgresql.ENUM(name="role_category_enum", create_type=False)
    employment = postgresql.ENUM(name="employment_type_enum", create_type=False)
    op.create_table(
        "auto_apply_authorizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_categories", postgresql.ARRAY(role), server_default="{}", nullable=False),
        sa.Column("employment_types", postgresql.ARRAY(employment), server_default="{}", nullable=False),
        sa.Column("locations", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("min_match_score", sa.SmallInteger(), server_default="70", nullable=False),
        sa.Column("max_per_day", sa.Integer(), server_default="5", nullable=False),
        sa.Column("max_per_session", sa.Integer(), server_default="2", nullable=False),
        sa.Column("resume_ids", postgresql.ARRAY(sa.Integer()), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("min_match_score >= 0 AND min_match_score <= 100", name="ck_auto_apply_min_score"),
        sa.CheckConstraint("max_per_day >= 0 AND max_per_day <= 25", name="ck_auto_apply_daily_limit"),
        sa.CheckConstraint("max_per_session >= 0 AND max_per_session <= 25", name="ck_auto_apply_session_limit"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_auto_apply_candidate"),
    )


def downgrade() -> None:
    op.drop_table("auto_apply_authorizations")
