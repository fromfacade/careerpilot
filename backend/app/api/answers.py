"""HTTP surface for the application answer library."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.enums import AnswerCategory, AnswerStatus
from app.schemas.answer import ApplicationAnswerCreate, ApplicationAnswerRead, ApplicationAnswerUpdate
from app.services import answer_service, candidate_service

router = APIRouter(prefix="/api/candidate/answers", tags=["application-answers"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ApplicationAnswerRead])
def list_answers(
    category: AnswerCategory | None = Query(default=None),
    status: AnswerStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    candidate = _require_candidate(db)
    return answer_service.list_answers(db, candidate, category=category, status=status, search=search)


@router.post("", response_model=ApplicationAnswerRead, status_code=201)
def create_answer(payload: ApplicationAnswerCreate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return answer_service.create_answer(
            db,
            candidate,
            question=payload.question,
            answer_text=payload.answer_text,
            category=payload.category,
            status=payload.status,
            is_reusable=payload.is_reusable,
            is_preferred=payload.is_preferred,
            prefer_not_to_answer=payload.prefer_not_to_answer,
            canonical_fact_ids=payload.canonical_fact_ids,
        )
    except (ConflictError, ValidationError, NotFoundError) as exc:
        code = 409 if isinstance(exc, ConflictError) else 404 if isinstance(exc, NotFoundError) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{answer_id}", response_model=ApplicationAnswerRead)
def read_answer(answer_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return answer_service.get_answer_or_404(db, candidate, answer_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{answer_id}", response_model=ApplicationAnswerRead)
def update_answer(answer_id: int, payload: ApplicationAnswerUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return answer_service.update_answer(
            db,
            candidate,
            answer_id,
            question=payload.question,
            answer_text=payload.answer_text,
            category=payload.category,
            status=payload.status,
            is_reusable=payload.is_reusable,
            is_preferred=payload.is_preferred,
            prefer_not_to_answer=payload.prefer_not_to_answer,
            canonical_fact_ids=payload.canonical_fact_ids,
        )
    except (ConflictError, ValidationError, NotFoundError) as exc:
        code = 409 if isinstance(exc, ConflictError) else 404 if isinstance(exc, NotFoundError) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/{answer_id}", status_code=204)
def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        answer_service.delete_answer(db, candidate, answer_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
