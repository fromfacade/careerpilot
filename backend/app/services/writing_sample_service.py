"""Writing samples: authentic user text used only as style references.

Never auto-classified as user writing. AI drafts can be adopted only
through an explicit `adopted_from_answer` action.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.answer import ApplicationAnswer
from app.models.candidate import Candidate
from app.models.enums import WritingSampleCategory, WritingSampleOrigin
from app.models.writing_sample import WritingSample
from app.services.answer_service import get_answer_or_404, question_fingerprint

MIN_SAMPLE_CHARS = 20
MAX_SAMPLE_CHARS = 4000
MAX_TITLE_CHARS = 200


def sample_fingerprint(body: str) -> str:
    return question_fingerprint(body)


def _normalize_body(body: str) -> str:
    text = re.sub(r"\s+", " ", (body or "").strip())
    if len(text) < MIN_SAMPLE_CHARS:
        raise ValidationError(f"Writing samples must be at least {MIN_SAMPLE_CHARS} characters.")
    if len(text) > MAX_SAMPLE_CHARS:
        raise ValidationError(f"Writing samples must be {MAX_SAMPLE_CHARS} characters or fewer.")
    return text


def list_samples(
    db: Session,
    candidate: Candidate,
    *,
    category: WritingSampleCategory | None = None,
    approved_only: bool = False,
) -> list[WritingSample]:
    stmt = select(WritingSample).where(WritingSample.candidate_id == candidate.id)
    if category is not None:
        stmt = stmt.where(WritingSample.category == category)
    if approved_only:
        stmt = stmt.where(WritingSample.is_approved_style_reference.is_(True))
    stmt = stmt.order_by(WritingSample.category, WritingSample.id)
    return list(db.execute(stmt).scalars().all())


def get_sample_or_404(db: Session, candidate: Candidate, sample_id: int) -> WritingSample:
    sample = db.execute(
        select(WritingSample).where(
            WritingSample.id == sample_id,
            WritingSample.candidate_id == candidate.id,
        )
    ).scalar_one_or_none()
    if sample is None:
        raise NotFoundError(f"No writing sample with id={sample_id} for this candidate.")
    return sample


def create_sample(
    db: Session,
    candidate: Candidate,
    *,
    body: str,
    title: str = "",
    category: WritingSampleCategory = WritingSampleCategory.GENERAL,
    origin: WritingSampleOrigin = WritingSampleOrigin.USER_WRITTEN,
    is_approved_style_reference: bool = False,
    source_answer_id: int | None = None,
) -> WritingSample:
    if origin is not WritingSampleOrigin.USER_WRITTEN and origin is not WritingSampleOrigin.ADOPTED_FROM_ANSWER:
        raise ValidationError("Writing samples cannot be stored as AI-generated text.")
    source: ApplicationAnswer | None = None
    if source_answer_id is not None:
        source = get_answer_or_404(db, candidate, source_answer_id)
        origin = WritingSampleOrigin.ADOPTED_FROM_ANSWER
        if not body.strip():
            body = source.answer_text
    elif origin is WritingSampleOrigin.ADOPTED_FROM_ANSWER:
        raise ValidationError("Adopting an answer as a writing sample requires source_answer_id.")
    normalized = _normalize_body(body)
    title_text = (title or "").strip()[:MAX_TITLE_CHARS]
    sample = WritingSample(
        candidate_id=candidate.id,
        title=title_text,
        body=normalized,
        content_fingerprint=sample_fingerprint(normalized),
        category=category,
        origin=origin,
        is_approved_style_reference=is_approved_style_reference,
        source_answer_id=source.id if source is not None else None,
    )
    db.add(sample)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An equivalent writing sample already exists.") from exc
    db.refresh(sample)
    return sample


def update_sample(
    db: Session,
    candidate: Candidate,
    sample_id: int,
    *,
    title: str | None = None,
    body: str | None = None,
    category: WritingSampleCategory | None = None,
    is_approved_style_reference: bool | None = None,
) -> WritingSample:
    sample = get_sample_or_404(db, candidate, sample_id)
    if title is not None:
        sample.title = title.strip()[:MAX_TITLE_CHARS]
    if body is not None:
        sample.body = _normalize_body(body)
        sample.content_fingerprint = sample_fingerprint(sample.body)
    if category is not None:
        sample.category = category
    if is_approved_style_reference is not None:
        sample.is_approved_style_reference = is_approved_style_reference
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An equivalent writing sample already exists.") from exc
    db.refresh(sample)
    return sample


def delete_sample(db: Session, candidate: Candidate, sample_id: int) -> None:
    sample = get_sample_or_404(db, candidate, sample_id)
    db.delete(sample)
    db.commit()
