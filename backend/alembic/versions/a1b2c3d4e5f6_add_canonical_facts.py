"""canonical candidate knowledge base

Revision ID: a1b2c3d4e5f6
Revises: c7e1a9d4f2b8
Create Date: 2026-10-26

Phase 2.2: an authoritative candidate profile that does not belong to any
one resume. Extracted `candidate_facts` stay as they are for traceability.
Canonical rows have no required resume FK; provenance links SET NULL when a
resume or extracted fact is deleted, so deleting an upload cannot wipe the
knowledge base.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c7e1a9d4f2b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    canonical_fact_status = postgresql.ENUM(
        "active", "conflict", "archived", name="canonical_fact_status_enum"
    )
    canonical_fact_origin = postgresql.ENUM(
        "resume_import", "manual_entry", "profile", name="canonical_fact_origin_enum"
    )
    canonical_fact_status.create(op.get_bind(), checkfirst=True)
    canonical_fact_origin.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "canonical_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column(
            "fact_type",
            postgresql.ENUM(name="fact_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("fact_key", sa.Text(), nullable=False),
        sa.Column("fact_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("identity_key", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="canonical_fact_status_enum", create_type=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "verification_status",
            postgresql.ENUM(name="fact_verification_status_enum", create_type=False),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "review_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("conflicts_with_id", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conflicts_with_id"], ["canonical_facts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_canonical_facts_active_identity",
        "canonical_facts",
        ["candidate_id", "identity_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_canonical_facts_candidate_status",
        "canonical_facts",
        ["candidate_id", "status"],
    )
    op.create_index(
        "ix_canonical_facts_fingerprint",
        "canonical_facts",
        ["candidate_id", "content_fingerprint"],
    )

    op.create_table(
        "canonical_fact_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_fact_id", sa.Integer(), nullable=False),
        sa.Column("candidate_fact_id", sa.Integer(), nullable=True),
        sa.Column("resume_id", sa.Integer(), nullable=True),
        sa.Column(
            "origin",
            postgresql.ENUM(name="canonical_fact_origin_enum", create_type=False),
            server_default="manual_entry",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["canonical_fact_id"], ["canonical_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_fact_id"], ["candidate_facts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_canonical_source_extracted_fact",
        "canonical_fact_sources",
        ["candidate_fact_id"],
        unique=True,
        postgresql_where=sa.text("candidate_fact_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_canonical_source_extracted_fact", table_name="canonical_fact_sources")
    op.drop_table("canonical_fact_sources")
    op.drop_index("ix_canonical_facts_fingerprint", table_name="canonical_facts")
    op.drop_index("ix_canonical_facts_candidate_status", table_name="canonical_facts")
    op.drop_index("uq_canonical_facts_active_identity", table_name="canonical_facts")
    op.drop_table("canonical_facts")
    op.execute("DROP TYPE IF EXISTS canonical_fact_origin_enum")
    op.execute("DROP TYPE IF EXISTS canonical_fact_status_enum")
