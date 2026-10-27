"""Application answer library.

Answers do not belong to a resume. Sensitive categories cannot jump from
`draft` to `approved` in one action. Equivalent question+answer pairs are
rejected as duplicates. At most one preferred answer per question.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.answer import ApplicationAnswer, ApplicationAnswerFact
from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import (
    AnswerCategory,
    AnswerOrigin,
    AnswerStatus,
    CanonicalFactStatus,
    SENSITIVE_ANSWER_CATEGORIES,
)
from app.models.enums import FactVerificationStatus

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def question_fingerprint(question: str) -> str:
    collapsed = _WS_RE.sub(" ", question).strip().casefold()
    return _PUNCT_RE.sub("", collapsed).strip()


def is_sensitive_category(category: AnswerCategory) -> bool:
    return category in SENSITIVE_ANSWER_CATEGORIES


def _assert_status_transition(answer: ApplicationAnswer, new_status: AnswerStatus) -> None:
    if new_status is answer.status:
        return
    if new_status is AnswerStatus.APPROVED and answer.is_sensitive and answer.status is AnswerStatus.DRAFT:
        raise ValidationError(
            "Sensitive answers cannot be approved directly from draft. "
            "Mark them reviewed first, then approve."
        )


def _assert_linkable_facts(db: Session, candidate: Candidate, fact_ids: list[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(fact_ids))
    if not unique_ids:
        return []
    rows = list(
        db.execute(
            select(CanonicalFact).where(
                CanonicalFact.id.in_(unique_ids),
                CanonicalFact.candidate_id == candidate.id,
            )
        ).scalars().all()
    )
    found = {row.id for row in rows}
    missing = [fid for fid in unique_ids if fid not in found]
    if missing:
        raise NotFoundError(f"Canonical facts {missing} were not found for this candidate.")
    unverified = [
        row.id
        for row in rows
        if row.verification_status not in {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}
        or row.status is not CanonicalFactStatus.ACTIVE
    ]
    if unverified:
        raise ValidationError(
            f"Canonical facts {unverified} are not active and verified/edited, so they cannot ground an answer."
        )
    return unique_ids


def _replace_fact_links(db: Session, answer: ApplicationAnswer, fact_ids: list[int], candidate: Candidate) -> None:
    unique_ids = _assert_linkable_facts(db, candidate, fact_ids)
    answer.fact_links.clear()
    db.flush()
    for fact_id in unique_ids:
        answer.fact_links.append(ApplicationAnswerFact(canonical_fact_id=fact_id))


def _clear_other_preferred(db: Session, candidate: Candidate, fingerprint: str, keep_id: int | None) -> None:
    stmt = select(ApplicationAnswer).where(
        ApplicationAnswer.candidate_id == candidate.id,
        ApplicationAnswer.question_fingerprint == fingerprint,
        ApplicationAnswer.is_preferred.is_(True),
    )
    if keep_id is not None:
        stmt = stmt.where(ApplicationAnswer.id != keep_id)
    for row in db.execute(stmt).scalars().all():
        row.is_preferred = False


def list_answers(
    db: Session,
    candidate: Candidate,
    *,
    category: AnswerCategory | None = None,
    status: AnswerStatus | None = None,
    search: str | None = None,
) -> list[ApplicationAnswer]:
    stmt = (
        select(ApplicationAnswer)
        .options(selectinload(ApplicationAnswer.fact_links))
        .where(ApplicationAnswer.candidate_id == candidate.id)
    )
    if category is not None:
        stmt = stmt.where(ApplicationAnswer.category == category)
    if status is not None:
        stmt = stmt.where(ApplicationAnswer.status == status)
    if search:
        needle = f"%{search.strip()}%"
        stmt = stmt.where(
            ApplicationAnswer.question.ilike(needle) | ApplicationAnswer.answer_text.ilike(needle)
        )
    stmt = stmt.order_by(ApplicationAnswer.category, ApplicationAnswer.id)
    return list(db.execute(stmt).scalars().all())


def get_answer_or_404(db: Session, candidate: Candidate, answer_id: int) -> ApplicationAnswer:
    answer = db.execute(
        select(ApplicationAnswer)
        .options(selectinload(ApplicationAnswer.fact_links))
        .where(ApplicationAnswer.id == answer_id, ApplicationAnswer.candidate_id == candidate.id)
    ).scalar_one_or_none()
    if answer is None:
        raise NotFoundError(f"No application answer with id={answer_id} for this candidate.")
    return answer


def create_answer(
    db: Session,
    candidate: Candidate,
    *,
    question: str,
    answer_text: str,
    category: AnswerCategory = AnswerCategory.OTHER,
    status: AnswerStatus = AnswerStatus.DRAFT,
    origin: AnswerOrigin = AnswerOrigin.MANUAL,
    is_reusable: bool = True,
    is_preferred: bool = False,
    prefer_not_to_answer: bool = False,
    canonical_fact_ids: list[int] | None = None,
    missing_information: list | None = None,
    generation_metadata: dict | None = None,
    rewritten_from_id: int | None = None,
    unsupported_claims: list | None = None,
) -> ApplicationAnswer:
    fingerprint = question_fingerprint(question)
    if not fingerprint:
        raise ValidationError("Question text is empty.")
    sensitive = is_sensitive_category(category)
    if status is AnswerStatus.APPROVED and sensitive:
        raise ValidationError(
            "Sensitive answers cannot be created as approved. Save as draft or reviewed first."
        )
    if prefer_not_to_answer:
        answer_text = ""
    if canonical_fact_ids:
        _assert_linkable_facts(db, candidate, canonical_fact_ids)
    row = ApplicationAnswer(
        candidate_id=candidate.id,
        question=question.strip(),
        question_fingerprint=fingerprint,
        answer_text=answer_text,
        category=category,
        status=status,
        origin=origin,
        is_reusable=is_reusable,
        is_preferred=False,
        is_sensitive=sensitive,
        prefer_not_to_answer=prefer_not_to_answer,
        missing_information=list(missing_information or []),
        generation_metadata=dict(generation_metadata or {}),
        rewritten_from_id=rewritten_from_id,
        unsupported_claims=list(unsupported_claims or []),
    )
    db.add(row)
    try:
        db.flush()
        if canonical_fact_ids:
            _replace_fact_links(db, row, canonical_fact_ids, candidate)
        if is_preferred:
            _clear_other_preferred(db, candidate, fingerprint, row.id)
            row.is_preferred = True
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An equivalent answer (same question and same text) already exists."
        ) from exc
    return get_answer_or_404(db, candidate, row.id)


def update_answer(
    db: Session,
    candidate: Candidate,
    answer_id: int,
    *,
    question: str | None = None,
    answer_text: str | None = None,
    category: AnswerCategory | None = None,
    status: AnswerStatus | None = None,
    is_reusable: bool | None = None,
    is_preferred: bool | None = None,
    prefer_not_to_answer: bool | None = None,
    canonical_fact_ids: list[int] | None = None,
) -> ApplicationAnswer:
    answer = get_answer_or_404(db, candidate, answer_id)
    if question is not None:
        fingerprint = question_fingerprint(question)
        if not fingerprint:
            raise ValidationError("Question text is empty.")
        answer.question = question.strip()
        answer.question_fingerprint = fingerprint
    if prefer_not_to_answer is True:
        answer.prefer_not_to_answer = True
        answer.answer_text = ""
    elif answer_text is not None:
        answer.answer_text = answer_text
        if prefer_not_to_answer is False:
            answer.prefer_not_to_answer = False
    if category is not None:
        answer.category = category
        answer.is_sensitive = is_sensitive_category(category)
    if status is not None:
        _assert_status_transition(answer, status)
        answer.status = status
    if is_reusable is not None:
        answer.is_reusable = is_reusable
    if canonical_fact_ids is not None:
        _replace_fact_links(db, answer, canonical_fact_ids, candidate)
    if is_preferred is True:
        _clear_other_preferred(db, candidate, answer.question_fingerprint, answer.id)
        answer.is_preferred = True
    elif is_preferred is False:
        answer.is_preferred = False
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An equivalent answer (same question and same text) already exists."
        ) from exc
    return get_answer_or_404(db, candidate, answer.id)


def delete_answer(db: Session, candidate: Candidate, answer_id: int) -> None:
    answer = get_answer_or_404(db, candidate, answer_id)
    db.delete(answer)
    db.commit()
