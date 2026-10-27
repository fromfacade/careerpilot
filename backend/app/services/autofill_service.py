"""Load candidate data and build an autofill plan.

The plan is data for review. This module does not open a browser, rewrite
answers, generate a resume, log answer text, or submit an application.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.autofill.mapping import AutofillPlan, FactView, ProfileView, plan_autofill
from app.autofill.materials import AnswerView, Materials, ResumeFileView, TailoredFileView
from app.autofill.urls import same_greenhouse_application
from app.models.candidate import Candidate
from app.models.enums import OPEN_PREPARATION_STATES
from app.models.resume import Resume
from app.models.writing_style import WritingStyleProfile
from app.services import answer_service, canonical_service, preparation_service


def build_plan(
    db: Session,
    candidate: Candidate,
    url: str,
    html: str,
    preparation_id: int | None = None,
) -> AutofillPlan:
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
    materials = _materials(db, candidate, url, preparation_id)
    return plan_autofill(url, html, facts, profile, materials)


def _materials(db: Session, candidate: Candidate, url: str, preparation_id: int | None) -> Materials:
    style = db.execute(
        select(WritingStyleProfile.id).where(WritingStyleProfile.candidate_id == candidate.id)
    ).scalar_one_or_none()
    library = [
        AnswerView(
            id=row.id,
            question=row.question,
            answer_text=row.answer_text,
            approval_status=row.status.value,
            origin=row.origin.value,
            category=row.category.value,
            is_sensitive=bool(row.is_sensitive),
            is_reusable=bool(row.is_reusable),
            is_preferred=bool(row.is_preferred),
            source="library",
        )
        for row in answer_service.list_answers(db, candidate)
    ]
    preparation, problem = _preparation(db, candidate, url, preparation_id)
    if preparation is None:
        return Materials(writing_style_profile_id=style, library_answers=library, link_problem=problem)
    resume = db.get(Resume, preparation.source_resume_id) if preparation.source_resume_id else None
    if resume is not None and resume.candidate_id != candidate.id:
        resume = None
    return Materials(
        preparation_id=preparation.id,
        resume=None
        if resume is None
        else ResumeFileView(
            resume_id=resume.id,
            display_name=resume.profile_name or resume.original_filename,
            file_format=resume.file_format.value,
            approved=bool(resume.is_approved),
            archived=bool(resume.is_archived),
            storage_path=resume.storage_path,
        ),
        tailored=TailoredFileView(
            status=preparation.tailored_resume_status.value,
            pdf_path=preparation.pdf_path,
            docx_path=preparation.docx_path,
        ),
        job_answers=[
            AnswerView(
                id=row.id,
                question=row.question,
                answer_text=row.answer_text,
                approval_status=row.status.value,
                origin=row.origin.value,
                category=row.category.value,
                is_sensitive=bool(row.is_sensitive),
                source="job_specific",
            )
            for row in preparation.answers
        ],
        library_answers=library,
        writing_style_profile_id=style,
        link_problem=problem,
    )


def _preparation(db: Session, candidate: Candidate, url: str, preparation_id: int | None):
    if preparation_id is not None:
        row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
        return _linked(db, row, url)
    matches = []
    for row in preparation_service.list_preparations(db, candidate):
        if row.state not in OPEN_PREPARATION_STATES:
            continue
        linked, problem = _linked(db, row, url)
        if linked is not None:
            matches.append(linked)
        elif problem and "not the same application" in problem:
            continue
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "More than one preparation matches this application. Choose one explicitly."
    return None, None


def _linked(db: Session, row, url: str):
    target, note = preparation_service.greenhouse_target(db, row)
    expected = target or row.snapshot_apply_url
    ok, problem = same_greenhouse_application(url, expected)
    if ok:
        return row, None
    if note and not target:
        problem = f"{note} {problem}"
    return None, problem
