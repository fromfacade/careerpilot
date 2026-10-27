"""Load the candidate knowledge base and build an autofill plan.

The plan is data for review. This module does not open a browser, change
HTML, or submit an application.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.autofill.mapping import AutofillPlan, FactView, ProfileView, plan_autofill
from app.models.candidate import Candidate
from app.services import canonical_service


def build_plan(db: Session, candidate: Candidate, url: str, html: str) -> AutofillPlan:
    facts = [
        FactView(
            id=row.id,
            fact_type=row.fact_type.value,
            fact_key=row.fact_key,
            fact_value=dict(row.fact_value or {}),
            identity_key=row.identity_key,
            status=row.status.value,
            verification_status=row.verification_status.value,
            needs_review=bool(row.needs_review),
            conflicts_with_id=row.conflicts_with_id,
            source_ids=tuple(source.id for source in row.sources),
            origins=tuple(source.origin.value for source in row.sources),
        )
        for row in canonical_service.list_canonical_facts(db, candidate)
    ]
    profile = ProfileView(
        candidate_id=candidate.id,
        full_name=candidate.full_name or "",
        email=candidate.email or "",
        phone=candidate.phone,
        location=candidate.current_location,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        portfolio_url=candidate.portfolio_url,
    )
    return plan_autofill(url, html, facts, profile)
