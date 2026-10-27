"""Job-specific application preparation.

Creates and updates review material for one job. This module never submits
an application or opens an employer form.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.ai.registry import get_provider
from app.ai.types import GenerationRequest
from app.core.config import get_settings
from app.core.exceptions import AIProviderError, NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import (
    AnswerCategory,
    AnswerStatus,
    CanonicalFactStatus,
    FactVerificationStatus,
    OPEN_PREPARATION_STATES,
    PreparationAnswerOrigin,
    PreparationItemStatus,
    PreparationState,
)
from app.models.job import Job
from app.models.job_source import JobSource
from app.models.preparation import ApplicationPreparation, ApplicationPreparationAnswer
from app.models.resume import Resume
from app.services import answer_service, canonical_service, resume_service
from app.services.answer_service import is_sensitive_category, question_fingerprint
from app.services.generation_service import (
    _SYSTEM,
    _format_fact,
    find_unsupported_claims,
    plan_draft,
    wrap_untrusted_sample,
)
from app.services.job_analysis import analyze_job_description, match_qualifications
from app.services.resume_export import export_docx, export_pdf
from app.services.resume_tailor import tailor_resume
from app.services.writing_style_service import format_profile_guidance


DESIGN_LIMITATION = (
    "The original resume's visual design is not reproduced. CareerPilot exports "
    "an ATS-friendly layout from verified facts. Download the original file to "
    "compare side by side."
)


def _load_job(db: Session, job_id: int) -> Job:
    job = db.execute(
        select(Job).options(joinedload(Job.job_source).joinedload(JobSource.employer)).where(Job.id == job_id)
    ).unique().scalar_one_or_none()
    if job is None:
        raise NotFoundError(f"No job with id={job_id}.")
    return job


def _primary_resume(db: Session, candidate: Candidate) -> Resume | None:
    return next((row for row in resume_service.list_resumes(db, candidate) if row.is_primary), None)


def get_open_preparation(db: Session, candidate: Candidate, job_id: int) -> ApplicationPreparation | None:
    return db.execute(
        select(ApplicationPreparation)
        .options(selectinload(ApplicationPreparation.answers))
        .where(
            ApplicationPreparation.candidate_id == candidate.id,
            ApplicationPreparation.job_id == job_id,
            ApplicationPreparation.state.in_(tuple(OPEN_PREPARATION_STATES)),
        )
    ).scalar_one_or_none()


def get_preparation_or_404(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = db.execute(
        select(ApplicationPreparation)
        .options(selectinload(ApplicationPreparation.answers))
        .where(
            ApplicationPreparation.id == preparation_id,
            ApplicationPreparation.candidate_id == candidate.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"No application preparation with id={preparation_id}.")
    return row


def list_preparations(db: Session, candidate: Candidate) -> list[ApplicationPreparation]:
    return list(
        db.execute(
            select(ApplicationPreparation)
            .options(selectinload(ApplicationPreparation.answers))
            .where(ApplicationPreparation.candidate_id == candidate.id)
            .order_by(ApplicationPreparation.id.desc())
        ).scalars().all()
    )


def create_or_get_preparation(db: Session, candidate: Candidate, job_id: int) -> ApplicationPreparation:
    existing = get_open_preparation(db, candidate, job_id)
    if existing is not None:
        return existing
    job = _load_job(db, job_id)
    if not (job.description_text or "").strip():
        raise ValidationError("This job has no description to prepare from.")
    employer = job.job_source.employer.name if job.job_source and job.job_source.employer else "Unknown employer"
    resume = _primary_resume(db, candidate)
    row = ApplicationPreparation(
        candidate_id=candidate.id,
        job_id=job.id,
        source_resume_id=resume.id if resume else None,
        state=PreparationState.PREPARING,
        snapshot_job_title=job.title,
        snapshot_employer=employer,
        snapshot_description=job.description_text,
        snapshot_apply_url=job.apply_url,
        snapshot_content_hash=job.content_hash,
        design_limitation=DESIGN_LIMITATION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return analyze_preparation(db, candidate, row.id)


def cancel_preparation(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    if row.state is PreparationState.CANCELLED:
        return row
    row.state = PreparationState.CANCELLED
    db.commit()
    db.refresh(row)
    return row


def _verified_facts(db: Session, candidate: Candidate):
    return [
        fact
        for fact in canonical_service.list_canonical_facts(
            db, candidate, status=CanonicalFactStatus.ACTIVE
        )
        if fact.verification_status in {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}
        and not fact.needs_review
    ]


def analyze_preparation(db: Session, candidate: Candidate, preparation_id: int) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    job = db.get(Job, row.job_id) if row.job_id else None
    row.analysis = analyze_job_description(row.snapshot_description, job)
    facts = _verified_facts(db, candidate)
    row.match_report = match_qualifications(row.analysis, facts, candidate)
    if not row.snapshot_description.strip():
        return mark_failed(db, row, "This job has no description to analyze.")
    row.tailored_resume = tailor_resume(candidate, facts, row.analysis)
    _export_tailored_files(row)
    fill_preparation_answers(db, candidate, row)
    row.state = PreparationState.NEEDS_REVIEW
    if not row.error_message.startswith("Tailored resume files"):
        row.error_message = ""
    db.commit()
    db.refresh(row)
    return get_preparation_or_404(db, candidate, row.id)


def _export_tailored_files(row: ApplicationPreparation) -> None:
    settings = get_settings()
    folder = Path(settings.preparation_storage_dir) / str(row.id)
    try:
        row.docx_path = str(export_docx(row.tailored_resume, folder / "tailored.docx"))
        row.pdf_path = str(export_pdf(row.tailored_resume, folder / "tailored.pdf"))
    except Exception as exc:  # export must not erase analysis or invent facts
        row.error_message = f"Tailored resume files could not be generated: {exc}"


def update_tailored_resume(db: Session, candidate: Candidate, preparation_id: int, payload) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    if payload.tailored_resume is not None:
        allowed = set(row.tailored_resume.get("source_fact_ids") or [])
        incoming_ids = set(payload.tailored_resume.get("source_fact_ids") or allowed)
        if incoming_ids - allowed:
            raise ValidationError("A tailored resume cannot add facts that were not already verified.")
        row.tailored_resume = payload.tailored_resume
        _export_tailored_files(row)
    if payload.status is not None:
        row.tailored_resume_status = payload.status
    mark_ready_if_approved(db, row)
    return get_preparation_or_404(db, candidate, row.id)


def _question_set(row: ApplicationPreparation) -> list[tuple[str, AnswerCategory]]:
    questions = [
        (f"Why are you interested in the {row.snapshot_job_title} role?", AnswerCategory.INTEREST),
        (f"Why do you want to work for {row.snapshot_employer}?", AnswerCategory.INTEREST),
        ("Tell us about a project you are proud of.", AnswerCategory.EXPERIENCE),
    ]
    techs = [item.get("text") for item in (row.analysis or {}).get("technologies") or [] if item.get("text")]
    if techs:
        questions.append((f"Describe your experience with {techs[0]}.", AnswerCategory.SKILLS))
    if (row.analysis or {}).get("work_authorization"):
        questions.append(("Are you authorized to work in the United States?", AnswerCategory.WORK_AUTHORIZATION))
    return questions


def fill_preparation_answers(db: Session, candidate: Candidate, row: ApplicationPreparation, provider=None) -> None:
    """Write preparation answers only. Never updates the answer library."""
    for item in list(row.answers):
        if item.status is not PreparationItemStatus.APPROVED:
            db.delete(item)
    db.flush()
    approved = answer_service.list_answers(db, candidate, status=AnswerStatus.APPROVED)
    by_fp = {item.question_fingerprint: item for item in approved if item.is_reusable}
    settings = get_settings()
    for question, category in _question_set(row):
        existing = next((item for item in row.answers if item.question == question), None)
        if existing is not None:
            continue
        if is_sensitive_category(category):
            row.answers.append(
                ApplicationPreparationAnswer(
                    question=question,
                    category=category,
                    origin=PreparationAnswerOrigin.REUSED,
                    status=PreparationItemStatus.NEEDS_REVIEW,
                    is_sensitive=True,
                    missing_information=["Sensitive questions are not drafted. Enter an authorized answer."],
                )
            )
            continue
        reused = by_fp.get(question_fingerprint(question))
        if reused is not None:
            row.answers.append(
                ApplicationPreparationAnswer(
                    question=question,
                    answer_text=reused.answer_text,
                    category=category,
                    origin=PreparationAnswerOrigin.REUSED,
                    status=PreparationItemStatus.DRAFT,
                    source_answer_id=reused.id,
                    canonical_fact_ids=[link.canonical_fact_id for link in reused.fact_links if link.canonical_fact_id],
                )
            )
            continue
        try:
            plan = plan_draft(db, candidate, question=question, category=category, job_id=row.job_id)
            facts_block = "\n".join(_format_fact(f) for f in plan.facts) or "(none)"
            if plan.job_block:
                facts_block = f"{facts_block}\n\nEmployer information (not a personal fact): {row.snapshot_employer}. {row.snapshot_description[:800]}"
            resolved = provider or get_provider(settings)
            result = resolved.generate(
                GenerationRequest(
                    question=question,
                    system_instruction=_SYSTEM,
                    facts_block=facts_block,
                    style_block="\n\n".join(f"Q: {a.question}\nA: {a.answer_text}" for a in plan.style_answers) or "(none)",
                    style_guidance=format_profile_guidance(plan.style_profile),
                    writing_samples_block="\n\n".join(wrap_untrusted_sample(s) for s in plan.writing_samples) or "(none)",
                    temperature=settings.ai_temperature,
                    max_output_tokens=settings.ai_max_output_tokens,
                    model=settings.ai_model,
                )
            )
            claims = find_unsupported_claims(result.text, facts_block=facts_block, original_text="")
            row.answers.append(
                ApplicationPreparationAnswer(
                    question=question,
                    answer_text=result.text,
                    category=category,
                    origin=PreparationAnswerOrigin.GENERATED,
                    status=PreparationItemStatus.DRAFT,
                    canonical_fact_ids=[f.id for f in plan.facts],
                    unsupported_claims=claims,
                    missing_information=plan.missing_information,
                )
            )
        except (AIProviderError, ValidationError) as exc:
            row.answers.append(
                ApplicationPreparationAnswer(
                    question=question,
                    category=category,
                    origin=PreparationAnswerOrigin.GENERATED,
                    status=PreparationItemStatus.NEEDS_REVIEW,
                    missing_information=[str(exc)],
                )
            )


def update_preparation_answer(
    db: Session,
    candidate: Candidate,
    preparation_id: int,
    answer_id: int,
    *,
    answer_text: str | None = None,
    status: PreparationItemStatus | None = None,
) -> ApplicationPreparation:
    row = get_preparation_or_404(db, candidate, preparation_id)
    item = next((ans for ans in row.answers if ans.id == answer_id), None)
    if item is None:
        raise NotFoundError(f"No preparation answer with id={answer_id}.")
    if status is PreparationItemStatus.APPROVED and item.is_sensitive and item.status is not PreparationItemStatus.NEEDS_REVIEW:
        raise ValidationError("Sensitive preparation answers must stay in needs_review until you edit and confirm them.")
    if item.is_sensitive and status is PreparationItemStatus.APPROVED and not (answer_text or item.answer_text).strip():
        raise ValidationError("A sensitive answer cannot be approved empty.")
    if answer_text is not None:
        item.answer_text = answer_text
    if status is not None:
        item.status = status
    mark_ready_if_approved(db, row)
    return get_preparation_or_404(db, candidate, row.id)


def mark_needs_review(db: Session, row: ApplicationPreparation) -> ApplicationPreparation:
    row.state = PreparationState.NEEDS_REVIEW
    row.error_message = ""
    db.commit()
    db.refresh(row)
    return row


def mark_failed(db: Session, row: ApplicationPreparation, message: str) -> ApplicationPreparation:
    row.state = PreparationState.FAILED
    row.error_message = message
    db.commit()
    db.refresh(row)
    return row


def mark_ready_if_approved(db: Session, row: ApplicationPreparation) -> ApplicationPreparation:
    answers = row.answers
    resume_ok = row.tailored_resume_status.value == "approved" if row.tailored_resume else False
    answers_ok = bool(answers) and all(item.status.value == "approved" for item in answers)
    if resume_ok and answers_ok:
        row.state = PreparationState.READY
    else:
        row.state = PreparationState.NEEDS_REVIEW
    db.commit()
    db.refresh(row)
    return row
