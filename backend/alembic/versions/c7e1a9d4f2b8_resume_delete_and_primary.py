"""resume delete safety and primary flag

Revision ID: c7e1a9d4f2b8
Revises: 6503438e5cd3
Create Date: 2026-10-26

Deleting a resume must not wipe independently verified candidate facts.
The previous ON DELETE CASCADE on candidate_facts.resume_id would do that.
SET NULL lets verified/edited facts survive as resume-independent rows.
is_primary marks which uploaded file is the current primary resume.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7e1a9d4f2b8"
down_revision: Union[str, None] = "6503438e5cd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
    )
    op.execute(
        """
        UPDATE resumes
        SET is_primary = true
        WHERE id IN (
            SELECT DISTINCT ON (candidate_id) id
            FROM resumes
            ORDER BY candidate_id, id ASC
        )
        """
    )
    op.create_index(
        "uq_resumes_one_primary_per_candidate",
        "resumes",
        ["candidate_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.drop_constraint("candidate_facts_resume_id_fkey", "candidate_facts", type_="foreignkey")
    op.create_foreign_key(
        "candidate_facts_resume_id_fkey",
        "candidate_facts",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("candidate_facts_resume_id_fkey", "candidate_facts", type_="foreignkey")
    op.create_foreign_key(
        "candidate_facts_resume_id_fkey",
        "candidate_facts",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("uq_resumes_one_primary_per_candidate", table_name="resumes")
    op.drop_column("resumes", "is_primary")
