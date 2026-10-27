"""answer rewrite provenance

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-26

Rewrites are new draft rows. The original answer is never overwritten.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_answers",
        sa.Column("rewritten_from_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "application_answers",
        sa.Column(
            "unsupported_claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_application_answers_rewritten_from",
        "application_answers",
        "application_answers",
        ["rewritten_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_application_answers_rewritten_from", "application_answers", type_="foreignkey")
    op.drop_column("application_answers", "unsupported_claims")
    op.drop_column("application_answers", "rewritten_from_id")
