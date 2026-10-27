"""application answer library

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-26

Reusable Q&A pairs, independent of resumes. Equivalent (question + answer)
rows are unique per candidate. At most one preferred answer per question
fingerprint. Links to canonical facts SET NULL if the fact is removed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    answer_category = postgresql.ENUM(
        "interest",
        "experience",
        "skills",
        "logistics",
        "work_authorization",
        "sponsorship",
        "disability",
        "veteran",
        "demographic",
        "criminal_history",
        "legal_attestation",
        "salary",
        "other",
        name="answer_category_enum",
    )
    answer_status = postgresql.ENUM("draft", "reviewed", "approved", name="answer_status_enum")
    answer_origin = postgresql.ENUM("manual", "ai_draft", name="answer_origin_enum")
    answer_category.create(op.get_bind(), checkfirst=True)
    answer_status.create(op.get_bind(), checkfirst=True)
    answer_origin.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "application_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_fingerprint", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(name="answer_category_enum", create_type=False),
            server_default="other",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="answer_status_enum", create_type=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "origin",
            postgresql.ENUM(name="answer_origin_enum", create_type=False),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("is_reusable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_preferred", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("prefer_not_to_answer", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "question_fingerprint",
            "answer_text",
            name="uq_application_answers_equivalent",
        ),
    )
    op.create_index(
        "ix_application_answers_candidate_category",
        "application_answers",
        ["candidate_id", "category"],
    )
    op.create_index(
        "ix_application_answers_fingerprint",
        "application_answers",
        ["candidate_id", "question_fingerprint"],
    )
    op.create_index(
        "uq_application_answers_preferred_per_question",
        "application_answers",
        ["candidate_id", "question_fingerprint"],
        unique=True,
        postgresql_where=sa.text("is_preferred IS TRUE"),
    )

    op.create_table(
        "application_answer_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("canonical_fact_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["answer_id"], ["application_answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_fact_id"], ["canonical_facts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", "canonical_fact_id", name="uq_answer_fact_link"),
    )


def downgrade() -> None:
    op.drop_table("application_answer_facts")
    op.drop_index("uq_application_answers_preferred_per_question", table_name="application_answers")
    op.drop_index("ix_application_answers_fingerprint", table_name="application_answers")
    op.drop_index("ix_application_answers_candidate_category", table_name="application_answers")
    op.drop_table("application_answers")
    op.execute("DROP TYPE IF EXISTS answer_origin_enum")
    op.execute("DROP TYPE IF EXISTS answer_status_enum")
    op.execute("DROP TYPE IF EXISTS answer_category_enum")
