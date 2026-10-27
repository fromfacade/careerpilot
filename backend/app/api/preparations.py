"""HTTP surface for application preparations. No submit endpoint exists."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.resume import Resume
from app.schemas.preparation import (
    ApplicationPreparationRead,
    PreparationAnswerUpdate,
    PreparationCreate,
    PreparationResumeSelect,
    TailoredResumeUpdate,
    to_read,
)
from app.services import candidate_service, preparation_service

router = APIRouter(prefix="/api/preparations", tags=["preparations"])


def _out(db: Session, row) -> ApplicationPreparationRead:
    resume = db.get(Resume, row.source_resume_id) if row.source_resume_id else None
    return to_read(row, resume)


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ApplicationPreparationRead])
def list_preparations(db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    return [_out(db, row) for row in preparation_service.list_preparations(db, candidate)]


@router.post("", response_model=ApplicationPreparationRead)
def create_preparation(payload: PreparationCreate, response: Response, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        existing = preparation_service.get_open_preparation(db, candidate, payload.job_id)
        row = preparation_service.create_or_get_preparation(db, candidate, payload.job_id)
        response.status_code = 200 if existing is not None else 201
        return _out(db, row)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{preparation_id}", response_model=ApplicationPreparationRead)
def read_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.get_preparation_or_404(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{preparation_id}/answers/{answer_id}", response_model=ApplicationPreparationRead)
def update_preparation_answer(
    preparation_id: int, answer_id: int, payload: PreparationAnswerUpdate, db: Session = Depends(get_db)
):
    candidate = _require_candidate(db)
    try:
        return _out(
            db,
            preparation_service.update_preparation_answer(
                db,
                candidate,
                preparation_id,
                answer_id,
                answer_text=payload.answer_text,
                status=payload.status,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{preparation_id}/regenerate", response_model=ApplicationPreparationRead)
def regenerate_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.regenerate_answers(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{preparation_id}/resume", response_model=ApplicationPreparationRead)
def update_tailored_resume(preparation_id: int, payload: TailoredResumeUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.update_tailored_resume(db, candidate, preparation_id, payload))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{preparation_id}/documents/{kind}")
def download_preparation_document(
    preparation_id: int,
    kind: str,
    db: Session = Depends(get_db),
    inline: bool = Query(False),
):
    candidate = _require_candidate(db)
    try:
        row = preparation_service.get_preparation_or_404(db, candidate, preparation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if kind == "docx":
        path = row.docx_path
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        name = "tailored-resume.docx"
    elif kind == "pdf":
        path = row.pdf_path
        media = "application/pdf"
        name = "tailored-resume.pdf"
    elif kind in {"original", "selected"}:
        resume = db.get(Resume, row.source_resume_id) if row.source_resume_id else None
        if resume is None or resume.candidate_id != candidate.id:
            raise HTTPException(status_code=404, detail="No original resume is attached to this preparation.")
        path = resume.storage_path
        media = "application/pdf" if resume.file_format.value == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        name = resume.original_filename
    else:
        raise HTTPException(status_code=404, detail="Unknown document kind.")
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="That prepared document is not available.")
    disposition = "inline" if inline and kind == "pdf" else "attachment"
    return FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition)


@router.post("/{preparation_id}/select-resume", response_model=ApplicationPreparationRead)
def select_preparation_resume(preparation_id: int, payload: PreparationResumeSelect, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.assign_selected_resume(db, candidate, preparation_id, payload.resume_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{preparation_id}/tailor", response_model=ApplicationPreparationRead)
def tailor_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.tailor_for_job(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{preparation_id}/tailor/revert", response_model=ApplicationPreparationRead)
def revert_preparation_tailoring(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.revert_tailoring(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{preparation_id}/cancel", response_model=ApplicationPreparationRead)
def cancel_preparation(preparation_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return _out(db, preparation_service.cancel_preparation(db, candidate, preparation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
