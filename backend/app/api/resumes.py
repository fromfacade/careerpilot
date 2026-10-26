from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import FileTooLargeError, NotFoundError, UnsupportedFileFormatError
from app.models.candidate import Candidate
from app.models.enums import FactType, FactVerificationStatus
from app.schemas.resume import CandidateFactRead, CandidateFactUpdate, ResumeRead, ResumeUploadResult
from app.services import candidate_service, resume_service

resumes_router = APIRouter(prefix="/api/resumes", tags=["resumes"])
facts_router = APIRouter(prefix="/api/candidate/facts", tags=["candidate-facts"])


def _require_candidate(db: Session) -> Candidate:
    try:
        return candidate_service.get_candidate_or_404(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@resumes_router.post("", response_model=ResumeUploadResult, status_code=201)
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    settings = get_settings()
    file_bytes = file.file.read()

    try:
        resume, facts_created = resume_service.upload_resume(
            db,
            candidate,
            filename=file.filename or "upload",
            content_type=file.content_type,
            file_bytes=file_bytes,
            storage_dir=Path(settings.resume_storage_dir),
            max_upload_mb=settings.resume_max_upload_mb,
        )
    except UnsupportedFileFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return ResumeUploadResult(resume=ResumeRead.model_validate(resume), facts_extracted=facts_created)


@resumes_router.get("", response_model=list[ResumeRead])
def list_resumes(db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    return resume_service.list_resumes(db, candidate)


@resumes_router.get("/{resume_id}", response_model=ResumeRead)
def read_resume(resume_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return resume_service.get_resume_or_404(db, candidate, resume_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@resumes_router.get("/{resume_id}/facts", response_model=list[CandidateFactRead])
def read_resume_facts(resume_id: int, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return resume_service.list_facts_for_resume(db, candidate, resume_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@facts_router.get("", response_model=list[CandidateFactRead])
def list_candidate_facts(
    fact_type: FactType | None = Query(default=None),
    verification_status: FactVerificationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    candidate = _require_candidate(db)
    return resume_service.list_candidate_facts(
        db, candidate, fact_type=fact_type, verification_status=verification_status
    )


@facts_router.patch("/{fact_id}", response_model=CandidateFactRead)
def update_candidate_fact(fact_id: int, payload: CandidateFactUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return resume_service.update_fact(db, candidate, fact_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
