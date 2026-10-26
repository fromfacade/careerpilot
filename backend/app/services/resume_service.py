"""Resume upload orchestration + the human fact-review actions.

Mirrors the existing module boundary pattern: this module takes explicit
config values (`storage_dir`, `max_upload_mb`) as parameters rather than
calling `get_settings()` itself, exactly like `app.sources.http.get_json`
takes explicit timeout/retry parameters instead of reaching into global
settings. The API layer fetches settings once and passes values down.
This keeps the service directly testable against a throwaway `tmp_path`
directory without monkeypatching global config.

Nothing here ever updates `candidates` table fields (graduation date,
work authorization, etc.) -- extracted facts live only in
`candidate_facts`, fully separate from the profile used by eligibility
scoring. See docs/architecture.md for why that separation is deliberate.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import FileTooLargeError, NotFoundError, ResumeExtractionError, UnsupportedFileFormatError
from app.models.candidate import Candidate
from app.models.enums import FactSource, FactType, FactVerificationStatus, ResumeFileFormat, ResumeParseStatus
from app.models.resume import CandidateFact, Resume
from app.resume_parsing.extractors import extract_text
from app.resume_parsing.section_parser import parse_resume_text
from app.schemas.resume import CandidateFactUpdate

_EXTENSION_TO_FORMAT: dict[str, ResumeFileFormat] = {
    ".pdf": ResumeFileFormat.PDF,
    ".docx": ResumeFileFormat.DOCX,
}
_ALLOWED_CONTENT_TYPES: dict[ResumeFileFormat, set[str]] = {
    ResumeFileFormat.PDF: {"application/pdf"},
    ResumeFileFormat.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        # Some browsers/OSes send this generic type for .docx uploads.
        "application/octet-stream",
    },
}


def resolve_file_format(filename: str, content_type: str | None) -> ResumeFileFormat:
    """Determine the resume format from its filename extension.

    Raises `UnsupportedFileFormatError` (-> HTTP 415) for anything not in
    the explicit .pdf/.docx allow-list. The extension is authoritative
    over the client-supplied content-type, which browsers/OSes are
    inconsistent about for .docx; a mismatching content-type (when one was
    actually provided) is still rejected as a sanity check.
    """
    suffix = Path(filename).suffix.lower()
    file_format = _EXTENSION_TO_FORMAT.get(suffix)
    if file_format is None:
        raise UnsupportedFileFormatError(
            f"Unsupported file extension '{suffix or '(none)'}'. Only .pdf and .docx are accepted."
        )
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES[file_format]:
        raise UnsupportedFileFormatError(f"Content-Type '{content_type}' does not match the '{suffix}' extension.")
    return file_format


def upload_resume(
    db: Session,
    candidate: Candidate,
    *,
    filename: str,
    content_type: str | None,
    file_bytes: bytes,
    storage_dir: Path,
    max_upload_mb: float,
) -> tuple[Resume, int]:
    """Validate, immutably persist, and parse an uploaded resume.

    The `Resume` row and the original file on disk are both written
    exactly once here and never updated by any other code path. A parsing
    failure (`ResumeExtractionError`) is caught and recorded on the
    `Resume` row (`parse_status=FAILED`) rather than propagated -- the
    original upload must never be lost just because extraction failed.
    Returns `(resume, facts_created)`.
    """
    max_bytes = int(max_upload_mb * 1024 * 1024)
    if len(file_bytes) == 0:
        raise UnsupportedFileFormatError("Uploaded file is empty.")
    if len(file_bytes) > max_bytes:
        raise FileTooLargeError(f"File is {len(file_bytes)} bytes, exceeding the {max_bytes}-byte limit.")

    file_format = resolve_file_format(filename, content_type)
    checksum = hashlib.sha256(file_bytes).hexdigest()

    storage_dir.mkdir(parents=True, exist_ok=True)
    # The stored filename is derived only from the checksum + validated
    # extension, never from client-supplied input -- no path-traversal
    # surface from `filename`.
    stored_name = f"{checksum}{Path(filename).suffix.lower()}"
    destination = storage_dir / stored_name
    if not destination.exists():
        destination.write_bytes(file_bytes)

    resume = Resume(
        candidate_id=candidate.id,
        original_filename=filename,
        file_format=file_format,
        storage_path=str(destination),
        file_size_bytes=len(file_bytes),
        sha256_checksum=checksum,
        parse_status=ResumeParseStatus.PENDING,
    )
    db.add(resume)
    db.flush()  # assign resume.id so CandidateFact rows below can reference it

    facts_created = 0
    try:
        text = extract_text(file_bytes, file_format)
        extracted = parse_resume_text(text)
        for fact in extracted:
            db.add(
                CandidateFact(
                    candidate_id=candidate.id,
                    resume_id=resume.id,
                    fact_type=fact.fact_type,
                    fact_key=fact.fact_key,
                    fact_value=fact.fact_value,
                    raw_text=fact.raw_text,
                    source=FactSource.RESUME_EXTRACTION,
                    verification_status=FactVerificationStatus.UNVERIFIED,
                )
            )
        facts_created = len(extracted)
        resume.parse_status = (
            ResumeParseStatus.PARTIAL
            if any(f.fact_type == FactType.OTHER for f in extracted)
            else ResumeParseStatus.SUCCESS
        )
    except ResumeExtractionError as exc:
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = str(exc)

    db.commit()
    db.refresh(resume)
    return resume, facts_created


def list_resumes(db: Session, candidate: Candidate) -> list[Resume]:
    stmt = select(Resume).where(Resume.candidate_id == candidate.id).order_by(Resume.id.desc())
    return list(db.execute(stmt).scalars().all())


def get_resume_or_404(db: Session, candidate: Candidate, resume_id: int) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.candidate_id != candidate.id:
        raise NotFoundError(f"No resume with id={resume_id} for this candidate.")
    return resume


def list_facts_for_resume(db: Session, candidate: Candidate, resume_id: int) -> list[CandidateFact]:
    get_resume_or_404(db, candidate, resume_id)  # 404s if not this candidate's resume
    stmt = (
        select(CandidateFact)
        .where(CandidateFact.resume_id == resume_id)
        .order_by(CandidateFact.fact_type, CandidateFact.id)
    )
    return list(db.execute(stmt).scalars().all())


def list_candidate_facts(
    db: Session,
    candidate: Candidate,
    *,
    fact_type: FactType | None = None,
    verification_status: FactVerificationStatus | None = None,
) -> list[CandidateFact]:
    stmt = select(CandidateFact).where(CandidateFact.candidate_id == candidate.id)
    if fact_type is not None:
        stmt = stmt.where(CandidateFact.fact_type == fact_type)
    if verification_status is not None:
        stmt = stmt.where(CandidateFact.verification_status == verification_status)
    stmt = stmt.order_by(CandidateFact.fact_type, CandidateFact.id)
    return list(db.execute(stmt).scalars().all())


def get_fact_or_404(db: Session, candidate: Candidate, fact_id: int) -> CandidateFact:
    fact = db.get(CandidateFact, fact_id)
    if fact is None or fact.candidate_id != candidate.id:
        raise NotFoundError(f"No candidate fact with id={fact_id} for this candidate.")
    return fact


def update_fact(db: Session, candidate: Candidate, fact_id: int, data: CandidateFactUpdate) -> CandidateFact:
    """The only mutation path for a `CandidateFact`. Editing content
    without explicitly specifying `verification_status` auto-promotes
    UNVERIFIED -> EDITED (still only ever triggered by an explicit human
    PATCH call, never automatically in the background) -- an explicit
    `verification_status` in the request always wins."""
    fact = get_fact_or_404(db, candidate, fact_id)
    updates = data.model_dump(exclude_unset=True)

    content_changed = False
    if updates.get("fact_key") is not None:
        fact.fact_key = updates["fact_key"]
        content_changed = True
    if updates.get("fact_value") is not None:
        fact.fact_value = updates["fact_value"]
        content_changed = True

    new_status = updates.get("verification_status")
    if new_status is None and content_changed:
        new_status = FactVerificationStatus.EDITED
    if new_status is not None:
        fact.verification_status = new_status
        fact.verified_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(fact)
    return fact
