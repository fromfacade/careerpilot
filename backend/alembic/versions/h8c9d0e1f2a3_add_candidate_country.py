"""candidate country for explicit Greenhouse dialing-country selection

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-10-27

Stores a country name the candidate entered. It is not inferred from a
shared dialing prefix.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "h8c9d0e1f2a3"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("country", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "country")
