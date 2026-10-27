"""HTTP surface for the writing style profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.schemas.writing_style import WritingStyleProfileRead, WritingStyleProfileUpdate
from app.services import candidate_service, writing_style_service

router = APIRouter(prefix="/api/candidate/writing-style", tags=["writing-style"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=WritingStyleProfileRead)
def read_writing_style(db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    return writing_style_service.get_or_create_profile(db, candidate)


@router.put("", response_model=WritingStyleProfileRead)
def replace_writing_style(payload: WritingStyleProfileUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return writing_style_service.update_profile(
            db,
            candidate,
            tone=payload.tone,
            formality=payload.formality,
            preferred_length=payload.preferred_length,
            sentence_complexity=payload.sentence_complexity,
            technical_detail=payload.technical_detail,
            vocabulary=payload.vocabulary,
            phrases_to_avoid=payload.phrases_to_avoid,
            additional_instructions=payload.additional_instructions,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
