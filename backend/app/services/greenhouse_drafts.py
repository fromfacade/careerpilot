"""Draft Greenhouse questions that have no approved answer.

This uses the existing grounded generation path. It does not submit an
application, and it does not call the model again when a draft is already
saved for the same question and application snapshot.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.registry import get_provider
from app.ai.types import GenerationRequest
from app.autofill.drafting import (
    GENERATION_FAILED,
    MISSING_FACTS,
    category_for,
    draft_action,
    fact_gap_message,
    limit_note,
    limit_text,
)
from app.autofill.greenhouse import question_kind_for
from app.core.config import get_settings
from app.core.exceptions import AIProviderError, ConflictError, ValidationError
from app.models.answer import ApplicationAnswer
from app.models.candidate import Candidate
from app.models.enums import (
    AnswerCategory,
    AnswerOrigin,
    AnswerStatus,
    PreparationAnswerOrigin,
    PreparationItemStatus,
)
from app.models.preparation import ApplicationPreparationAnswer
from app.services import answer_service, preparation_service
from app.services.answer_service import question_fingerprint
from app.services.generation_service import (
    _SYSTEM,
    _format_fact,
    find_unsupported_claims,
    plan_draft,
    wrap_untrusted_sample,
)
from app.services.job_analysis import employer_context
from app.services.preparation_service import _INTEREST_RULES
from app.services.writing_style_service import format_profile_guidance


def ensure_form_drafts(db: Session, candidate: Candidate, preparation_id: int, plan, *, provider=None) -> int:
    """Save a draft for each open no_match question that does not have one yet."""
    row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
    saved = {question_fingerprint(item.question): item for item in row.answers}
    seen = set(saved)
    written = 0
    for proposal in plan.answers.missing:
        if proposal.match_kind != "no_match":
            continue
        label = proposal.label.strip()
        fingerprint = question_fingerprint(label)
        if not label or not fingerprint:
            continue
        action = draft_action(question_kind_for(label), label)
        if action in {"manual", "skip"}:
            continue
        if fingerprint in seen:
            existing = saved.get(fingerprint)
            if (
                isinstance(existing, ApplicationPreparationAnswer)
                and action == "generate"
                and existing.status in {PreparationItemStatus.DRAFT, PreparationItemStatus.NEEDS_REVIEW}
                and _context_changed(db, existing, row)
            ):
                _write_generated(db, candidate, preparation_id, label, provider=provider, replace=existing)
                written += 1
            continue
        if action == "fact":
            _append_answer(
                db,
                candidate,
                preparation_id,
                question=label,
                answer_text="",
                category=AnswerCategory.LOGISTICS,
                status=PreparationItemStatus.NEEDS_REVIEW,
                missing_information=[fact_gap_message(question_kind_for(label))],
            )
            seen.add(fingerprint)
            written += 1
            continue
        _write_generated(db, candidate, preparation_id, label, provider=provider, replace=None)
        seen.add(fingerprint)
        written += 1
    return written


def regenerate_form_draft(
    db: Session,
    candidate: Candidate,
    preparation_id: int,
    question: str,
    *,
    provider=None,
) -> ApplicationPreparationAnswer:
    """Replace one saved draft because the user asked for a new one."""
    label = question.strip()
    action = draft_action(question_kind_for(label), label)
    if action != "generate":
        raise ValidationError("This question is not drafted automatically.")
    row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
    fingerprint = question_fingerprint(label)
    existing = next((item for item in row.answers if question_fingerprint(item.question) == fingerprint), None)
    if existing is not None and existing.is_sensitive:
        raise ValidationError("Sensitive questions stay manual.")
    return _write_generated(db, candidate, preparation_id, label, provider=provider, replace=existing)


def _write_generated(db, candidate, preparation_id, label, *, provider, replace):
    row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
    category = category_for(label)
    try:
        drafted = plan_draft(db, candidate, question=label, category=category)
    except ValidationError:
        return _append_answer(
            db,
            candidate,
            preparation_id,
            question=label,
            answer_text="",
            category=category,
            status=PreparationItemStatus.NEEDS_REVIEW,
            missing_information=[MISSING_FACTS],
            replace=replace,
        )
    if category is not AnswerCategory.INTEREST and not drafted.facts:
        return _append_answer(
            db,
            candidate,
            preparation_id,
            question=label,
            answer_text="",
            category=category,
            status=PreparationItemStatus.NEEDS_REVIEW,
            missing_information=list(drafted.missing_information) or [MISSING_FACTS],
            replace=replace,
        )
    facts_block = _facts_block(drafted, row)
    settings = get_settings()
    instruction = _SYSTEM + (_INTEREST_RULES if category is AnswerCategory.INTEREST else "")
    try:
        resolved = provider or get_provider(settings)
        result = resolved.generate(
            GenerationRequest(
                question=_model_question(label, row),
                system_instruction=instruction,
                facts_block=facts_block,
                style_block="\n\n".join(f"Q: {item.question}\nA: {item.answer_text}" for item in drafted.style_answers)
                or "(none)",
                style_guidance=format_profile_guidance(drafted.style_profile),
                writing_samples_block="\n\n".join(wrap_untrusted_sample(sample) for sample in drafted.writing_samples)
                or "(none)",
                temperature=settings.ai_temperature,
                max_output_tokens=settings.ai_max_output_tokens,
                model=settings.ai_model,
            )
        )
    except AIProviderError:
        return _append_answer(
            db,
            candidate,
            preparation_id,
            question=label,
            answer_text="",
            category=category,
            status=PreparationItemStatus.NEEDS_REVIEW,
            missing_information=[GENERATION_FAILED],
            canonical_fact_ids=[fact.id for fact in drafted.facts],
            replace=replace,
        )
    text, shortened = limit_text(result.text, label)
    claims = find_unsupported_claims(text, facts_block=facts_block, original_text="")
    missing = list(drafted.missing_information)
    if shortened:
        missing.append("The draft was shortened to the question's limit.")
    library = _library_draft(
        db,
        candidate,
        label=label,
        text=text,
        category=category,
        fact_ids=[fact.id for fact in drafted.facts],
        missing=missing,
        claims=claims,
        metadata={
            "provider": result.provider,
            "model": result.model,
            "usage": result.raw_usage,
            "style_profile_id": drafted.style_profile.id,
            "employer": row.snapshot_employer,
            "job_title": row.snapshot_job_title,
            "preparation_id": row.id,
            "context_key": _context_key(row),
        },
        existing_id=replace.source_answer_id if replace is not None else None,
    )
    return _append_answer(
        db,
        candidate,
        preparation_id,
        question=label,
        answer_text=text,
        category=category,
        status=PreparationItemStatus.DRAFT,
        canonical_fact_ids=[fact.id for fact in drafted.facts],
        unsupported_claims=claims,
        missing_information=missing,
        source_answer_id=library.id if library is not None else None,
        replace=replace,
    )


def _facts_block(drafted, row) -> str:
    facts_block = "\n".join(_format_fact(fact) for fact in drafted.facts) or "(none)"
    context = employer_context(row.analysis or {}, row.snapshot_employer, row.snapshot_job_title)
    posting = (row.snapshot_description or "").strip()[:1500]
    if posting:
        context = f"{context}\nJob description:\n{posting}".strip()
    if context:
        facts_block = (
            f"{facts_block}\n\nEmployer information (not a personal fact; do not treat as a qualification):\n{context}"
        )
    return facts_block


def _model_question(label: str, row) -> str:
    return (
        f"{label}\n\nApplication: {row.snapshot_job_title} at {row.snapshot_employer}. "
        f"{limit_note(label)}"
    )


def _context_key(row) -> str:
    description = row.snapshot_description or ""
    return "|".join(
        (
            (row.snapshot_employer or "").strip().casefold(),
            (row.snapshot_job_title or "").strip().casefold(),
            str(len(description)),
            description[:80].casefold(),
        )
    )


def _context_changed(db, answer, row) -> bool:
    if answer.source_answer_id is None:
        return False
    library = db.get(ApplicationAnswer, answer.source_answer_id)
    if library is None:
        return False
    stored = (library.generation_metadata or {}).get("context_key")
    if not stored:
        return False
    return stored != _context_key(row)


def _library_draft(db, candidate, *, label, text, category, fact_ids, missing, claims, metadata, existing_id):
    if existing_id is not None:
        library = db.get(ApplicationAnswer, existing_id)
        if library is not None and library.candidate_id == candidate.id and library.status is not AnswerStatus.APPROVED:
            library.answer_text = text
            library.missing_information = list(missing)
            library.unsupported_claims = list(claims)
            library.generation_metadata = dict(metadata)
            library.status = AnswerStatus.DRAFT
            library.is_reusable = False
            db.commit()
            return library
    try:
        return answer_service.create_answer(
            db,
            candidate,
            question=label,
            answer_text=text,
            category=category,
            status=AnswerStatus.DRAFT,
            origin=AnswerOrigin.AI_DRAFT,
            is_reusable=False,
            canonical_fact_ids=fact_ids,
            missing_information=missing,
            generation_metadata=metadata,
            unsupported_claims=claims,
        )
    except ConflictError:
        return db.execute(
            select(ApplicationAnswer).where(
                ApplicationAnswer.candidate_id == candidate.id,
                ApplicationAnswer.question_fingerprint == question_fingerprint(label),
                ApplicationAnswer.answer_text == text,
            )
        ).scalar_one_or_none()


def _append_answer(db, candidate, preparation_id, *, replace=None, **fields):
    row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
    target = None
    if replace is not None:
        target = next((item for item in row.answers if item.id == replace.id), None)
    if target is None:
        target = ApplicationPreparationAnswer(
            question=fields["question"],
            origin=PreparationAnswerOrigin.GENERATED,
        )
        row.answers.append(target)
    target.question = fields["question"]
    target.answer_text = fields.get("answer_text", "")
    target.category = fields["category"]
    target.origin = PreparationAnswerOrigin.GENERATED
    target.status = fields["status"]
    target.is_sensitive = False
    target.canonical_fact_ids = list(fields.get("canonical_fact_ids") or [])
    target.unsupported_claims = list(fields.get("unsupported_claims") or [])
    target.missing_information = list(fields.get("missing_information") or [])
    if "source_answer_id" in fields:
        target.source_answer_id = fields["source_answer_id"]
    db.commit()
    db.refresh(target)
    return target
