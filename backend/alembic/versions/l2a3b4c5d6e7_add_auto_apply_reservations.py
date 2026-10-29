"""auto-apply reservations and submission initiation

Revision ID: l2a3b4c5d6e7
Revises: k1f2a3b4c5d6
Create Date: 2026-10-28

A held reservation is the slot claimed before an Auto-Apply click.
Application events record whether that click came from Review Mode or
from the grant. They do not store answers or credentials.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l2a3b4c5d6e7"
down_revision: Union[str, None] = "k1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application_events", sa.Column("initiation", sa.Text(), nullable=True))
    op.add_column("application_events", sa.Column("authorization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_application_events_authorization",
        "application_events",
        "auto_apply_authorizations",
        ["authorization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_application_event_initiation",
        "application_events",
        "initiation IS NULL OR initiation IN ('review', 'auto_apply')",
    )
    op.create_table(
        "auto_apply_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('held', 'released', 'settled')", name="ck_auto_apply_reservation_state"),
        sa.ForeignKeyConstraint(["authorization_id"], ["auto_apply_authorizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["tracked_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_auto_apply_reservation_held",
        "auto_apply_reservations",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("state = 'held'"),
    )


def downgrade() -> None:
    op.drop_index("uq_auto_apply_reservation_held", table_name="auto_apply_reservations")
    op.drop_table("auto_apply_reservations")
    op.drop_constraint("ck_application_event_initiation", "application_events", type_="check")
    op.drop_constraint("fk_application_events_authorization", "application_events", type_="foreignkey")
    op.drop_column("application_events", "authorization_id")
    op.drop_column("application_events", "initiation")
