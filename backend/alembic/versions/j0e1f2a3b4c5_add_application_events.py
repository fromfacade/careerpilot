"""application event history

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-10-27

Append-only status changes for one tracked application. Notes stay short
and redacted. No answers or credentials are stored.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "j0e1f2a3b4c5"
down_revision: Union[str, None] = "i9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracked_applications", sa.Column("resubmit_after", sa.DateTime(timezone=True), nullable=True))
    source = postgresql.ENUM("browser", "manual", name="application_event_source_enum")
    source.create(op.get_bind(), checkfirst=True)
    status = postgresql.ENUM(name="application_status_enum", create_type=False)
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("previous_status", status, nullable=False),
        sa.Column("new_status", status, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(name="application_event_source_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["tracked_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_events_application_id", "application_events", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")
    postgresql.ENUM(name="application_event_source_enum").drop(op.get_bind(), checkfirst=True)
    op.drop_column("tracked_applications", "resubmit_after")
