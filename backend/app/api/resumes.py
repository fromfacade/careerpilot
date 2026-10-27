from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import (
    ConflictError,
    FileTooLargeError,
    NotFoundError,
    ResumeExtractionError,
    UnsupportedFileFormatError,
    ValidationError,
)
from app.models.candidate import Candidate
from app.models.enums import FactType, FactVerificationStatus
from app.schemas.resume import (
    CandidateFactBulkUpdate,
    CandidateFactRead,
    CandidateFactUpdate,
    ResumeDeleteRequest,
    ResumeDeleteResult,
    ResumeRead,
    ResumeReprocessResult,
    ResumeUploadResult,
)
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
        outcome = resume_service.upload_resume(
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

    return ResumeUploadResult(
        resume=ResumeRead.model_validate(outcome.resume),
        facts_extracted=outcome.facts_created,
        facts_skipped_duplicate=outcome.facts_skipped_duplicate,
        already_uploaded=outcome.already_uploaded,
    )


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


@resumes_router.post("/{resume_id}/reprocess", response_model=ResumeReprocessResult)
def reprocess_resume(resume_id: int, db: Session = Depends(get_db)):
    """Re-parse the original stored file. Replaces UNVERIFIED facts only;
    verified / edited / rejected facts and the file itself are untouched."""
    candidate = _require_candidate(db)
    try:
        outcome = resume_service.reprocess_resume(db, candidate, resume_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResumeExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ResumeReprocessResult(
        resume=ResumeRead.model_validate(outcome.resume),
        facts_extracted=outcome.facts_extracted,
        facts_replaced=outcome.facts_replaced,
        facts_preserved=outcome.facts_preserved,
        facts_skipped_duplicate=outcome.facts_skipped_duplicate,
    )


@resumes_router.post("/{resume_id}/primary", response_model=ResumeRead)
def mark_primary_resume(resume_id: int, db: Session = Depends(get_db)):
    """Set this uploaded file as the primary resume. File bytes are not changed."""
    candidate = _require_candidate(db)
    try:
        return resume_service.set_primary_resume(db, candidate, resume_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@resumes_router.delete("/{resume_id}", response_model=ResumeDeleteResult)
def delete_resume(
    resume_id: int,
    payload: ResumeDeleteRequest = Body(default_factory=ResumeDeleteRequest),
    db: Session = Depends(get_db),
):
    """Delete one uploaded resume.

    Default: remove the file and unverified/rejected facts extracted from
    it. Verified and edited facts stay as independent candidate records
    unless `delete_verified_facts` is true. Facts from other resumes,
    the candidate profile, preferences, job listings, and saved jobs are
    not modified.
    """
    candidate = _require_candidate(db)
    try:
        facts_deleted, facts_preserved, primary_resume_id = resume_service.delete_resume(
            db,
            candidate,
            resume_id,
            delete_verified_facts=payload.delete_verified_facts,
            replacement_resume_id=payload.replacement_resume_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ResumeDeleteResult(
        deleted_resume_id=resume_id,
        facts_deleted=facts_deleted,
        facts_preserved=facts_preserved,
        primary_resume_id=primary_resume_id,
    )


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


@facts_router.post("/bulk", response_model=list[CandidateFactRead])
def bulk_update_candidate_facts(payload: CandidateFactBulkUpdate, db: Session = Depends(get_db)):
    """Explicit bulk verify/reject. Never called automatically."""
    candidate = _require_candidate(db)
    try:
        return resume_service.update_facts_bulk(
            db, candidate, payload.fact_ids, payload.verification_status
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@facts_router.patch("/{fact_id}", response_model=CandidateFactRead)
def update_candidate_fact(fact_id: int, payload: CandidateFactUpdate, db: Session = Depends(get_db)):
    candidate = _require_candidate(db)
    try:
        return resume_service.update_fact(db, candidate, fact_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
