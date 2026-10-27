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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    FileTooLargeError,
    NotFoundError,
    ResumeExtractionError,
    UnsupportedFileFormatError,
    ValidationError,
)
from app.models.candidate import Candidate
from app.models.enums import (
    FactSource,
    FactType,
    FactVerificationStatus,
    ResumeCategory,
    ResumeFileFormat,
    ResumeParseStatus,
)
from app.models.resume import CandidateFact, Resume
from app.resume_parsing.dedupe import partition_extracted
from app.resume_parsing.extractors import extract_text
from app.resume_parsing.section_parser import parse_resume_text
from app.resume_parsing.types import ExtractedFact
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
) -> UploadOutcome:
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

    # Uploading byte-identical content again must not create a second resume
    # (and a second set of unverified facts). Return the existing one.
    same_file = db.execute(
        select(Resume).where(Resume.candidate_id == candidate.id, Resume.sha256_checksum == checksum).limit(1)
    ).scalar_one_or_none()
    if same_file is not None:
        return UploadOutcome(resume=same_file, facts_created=0, facts_skipped_duplicate=0, already_uploaded=True)

    storage_dir.mkdir(parents=True, exist_ok=True)
    # The stored filename is derived only from the checksum + validated
    # extension, never from client-supplied input -- no path-traversal
    # surface from `filename`.
    stored_name = f"{checksum}{Path(filename).suffix.lower()}"
    destination = storage_dir / stored_name
    if not destination.exists():
        destination.write_bytes(file_bytes)

    existing = db.execute(select(Resume.id).where(Resume.candidate_id == candidate.id).limit(1)).first()
    resume = Resume(
        candidate_id=candidate.id,
        original_filename=filename,
        file_format=file_format,
        storage_path=str(destination),
        file_size_bytes=len(file_bytes),
        sha256_checksum=checksum,
        parse_status=ResumeParseStatus.PENDING,
        is_primary=existing is None,
        profile_name=Path(filename).stem or filename,
        category=ResumeCategory.CUSTOM,
        is_approved=False,
        is_archived=False,
        focus_areas=[],
    )
    db.add(resume)
    db.flush()  # assign resume.id so CandidateFact rows below can reference it

    created, skipped = _apply_extracted_facts(db, candidate, resume, file_bytes, file_format)

    db.commit()
    db.refresh(resume)
    return UploadOutcome(resume=resume, facts_created=created, facts_skipped_duplicate=skipped, already_uploaded=False)


@dataclass
class UploadOutcome:
    resume: Resume
    facts_created: int
    facts_skipped_duplicate: int
    already_uploaded: bool


@dataclass
class ReprocessOutcome:
    resume: Resume
    facts_extracted: int
    facts_replaced: int
    facts_preserved: int
    facts_skipped_duplicate: int


_REVIEWED_STATUSES = (FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED)


def _reviewed_candidate_facts(db: Session, candidate: Candidate) -> list[CandidateFact]:
    """Every verified/edited fact for the candidate, across all resumes
    (including ones detached from a deleted resume). Read-only reference."""
    stmt = select(CandidateFact).where(
        CandidateFact.candidate_id == candidate.id,
        CandidateFact.verification_status.in_(_REVIEWED_STATUSES),
    )
    return list(db.execute(stmt).scalars().all())


def _insert_extracted(
    db: Session,
    candidate: Candidate,
    resume: Resume,
    extracted: list[ExtractedFact],
    *,
    suppress: list[CandidateFact] | None = None,
) -> tuple[int, int]:
    """Insert UNVERIFIED facts for `resume`, skipping duplicates of facts
    the candidate already reviewed. Returns `(created, skipped_duplicates)`.

    Facts are only ever added to `resume`; no other resume's records are
    read for modification, so uploads stay isolated from older resumes.
    """
    result = partition_extracted(
        extracted,
        reviewed=_reviewed_candidate_facts(db, candidate),
        suppress=suppress or [],
    )
    for fact in result.to_create:
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
    return len(result.to_create), result.skipped_duplicates


def _parse_status_for(extracted: list[ExtractedFact]) -> ResumeParseStatus:
    return (
        ResumeParseStatus.PARTIAL
        if any(f.fact_type == FactType.OTHER for f in extracted)
        else ResumeParseStatus.SUCCESS
    )


def _apply_extracted_facts(
    db: Session,
    candidate: Candidate,
    resume: Resume,
    file_bytes: bytes,
    file_format: ResumeFileFormat,
) -> tuple[int, int]:
    """Extract + parse `file_bytes` and insert UNVERIFIED facts for `resume`.

    Parse status is set here. Used only for the first parse on upload.
    Returns `(created, skipped_duplicates)`.
    """
    try:
        text = extract_text(file_bytes, file_format)
        extracted = parse_resume_text(text)
        created, skipped = _insert_extracted(db, candidate, resume, extracted)
        resume.parse_status = _parse_status_for(extracted)
        resume.parse_error = None
        return created, skipped
    except ResumeExtractionError as exc:
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = str(exc)
        return 0, 0


def reprocess_resume(db: Session, candidate: Candidate, resume_id: int) -> ReprocessOutcome:
    """Re-parse the original stored file and replace UNVERIFIED facts only.

    The resume row and the file on disk are never deleted. Facts the
    candidate has already verified, edited, or rejected are preserved, and
    re-extracted facts that duplicate them are skipped rather than
    re-inserted.

    Extraction is attempted *before* any delete so a parse failure cannot
    wipe existing unverified facts.
    """
    resume = get_resume_or_404(db, candidate, resume_id)
    stored = Path(resume.storage_path)
    if not stored.is_file():
        raise NotFoundError(
            f"Stored resume file for id={resume_id} is missing; the original upload cannot be reprocessed."
        )

    file_bytes = stored.read_bytes()
    # Dry-run extract/parse first so a failure leaves existing facts intact.
    text = extract_text(file_bytes, resume.file_format)
    extracted = parse_resume_text(text)

    existing = list_facts_for_resume(db, candidate, resume_id)
    preserved = [
        fact
        for fact in existing
        if fact.verification_status
        in {
            FactVerificationStatus.VERIFIED,
            FactVerificationStatus.EDITED,
            FactVerificationStatus.REJECTED,
        }
    ]
    replaced = [fact for fact in existing if fact not in preserved]
    for fact in replaced:
        db.delete(fact)
    db.flush()

    # Facts the user rejected in this resume must not be resurrected by a
    # reprocess; verified/edited ones are matched via the reviewed set.
    rejected_here = [f for f in preserved if f.verification_status == FactVerificationStatus.REJECTED]
    created, skipped = _insert_extracted(db, candidate, resume, extracted, suppress=rejected_here)
    resume.parse_status = _parse_status_for(extracted)
    resume.parse_error = None

    db.commit()
    db.refresh(resume)
    return ReprocessOutcome(
        resume=resume,
        facts_extracted=created,
        facts_replaced=len(replaced),
        facts_preserved=len(preserved),
        facts_skipped_duplicate=skipped,
    )


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


def update_facts_bulk(
    db: Session,
    candidate: Candidate,
    fact_ids: list[int],
    verification_status: FactVerificationStatus,
) -> list[CandidateFact]:
    """Apply one explicit review status to many facts. Missing IDs 404
    rather than silently skipping, so a stale selection cannot look like
    it succeeded. Never used automatically -- the API is the only caller.

    Bulk *verification* refuses any fact the parser flagged `needs_review`
    (ambiguous or conflicting). Those must be reviewed individually so
    uncertain information is never verified in one click. Every fact is
    checked before any is changed, so a refused request changes nothing.
    """
    ordered_ids = list(dict.fromkeys(fact_ids))
    facts = [get_fact_or_404(db, candidate, fact_id) for fact_id in ordered_ids]
    if verification_status == FactVerificationStatus.VERIFIED:
        flagged = [f.id for f in facts if (f.fact_value or {}).get("needs_review")]
        if flagged:
            raise ValidationError(
                f"Facts {flagged} are flagged for review and cannot be bulk-verified. "
                "Review and verify or edit them individually."
            )
    updated: list[CandidateFact] = []
    for fact in facts:
        fact.verification_status = verification_status
        fact.verified_at = datetime.now(timezone.utc)
        updated.append(fact)
    db.commit()
    for fact in updated:
        db.refresh(fact)
    return updated


_INDEPENDENT_FACT_STATUSES = frozenset(
    {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}
)


def set_primary_resume(db: Session, candidate: Candidate, resume_id: int) -> Resume:
    """Mark `resume_id` as the only primary resume for this candidate."""
    resume = get_resume_or_404(db, candidate, resume_id)
    others = list(
        db.execute(
            select(Resume).where(Resume.candidate_id == candidate.id, Resume.id != resume.id)
        ).scalars().all()
    )
    for other in others:
        other.is_primary = False
    resume.is_primary = True
    db.commit()
    db.refresh(resume)
    return resume


def update_resume_profile(db: Session, candidate: Candidate, resume_id: int, payload) -> Resume:
    resume = get_resume_or_404(db, candidate, resume_id)
    if payload.profile_name is not None:
        resume.profile_name = payload.profile_name.strip()
    if payload.profile_description is not None:
        resume.profile_description = payload.profile_description.strip()
    if payload.category is not None:
        resume.category = payload.category
    if payload.is_approved is not None:
        resume.is_approved = payload.is_approved
    if payload.is_archived is not None:
        resume.is_archived = payload.is_archived
    if payload.focus_areas is not None:
        resume.focus_areas = [str(item).strip() for item in payload.focus_areas if str(item).strip()]
    if payload.is_primary is True:
        return set_primary_resume(db, candidate, resume_id)
    db.commit()
    db.refresh(resume)
    return resume


def list_approved_resumes(db: Session, candidate: Candidate) -> list[Resume]:
    return [
        row
        for row in list_resumes(db, candidate)
        if row.is_approved and not row.is_archived
    ]


def delete_resume(
    db: Session,
    candidate: Candidate,
    resume_id: int,
    *,
    delete_verified_facts: bool = False,
    replacement_resume_id: int | None = None,
) -> tuple[int, int, int | None]:
    """Delete one resume and only that resume's extracted records.

    Default: unverified/rejected facts for this file are removed; verified
    and edited facts are detached (`resume_id=NULL`) so they remain as
    independent candidate information. `delete_verified_facts=True` is the
    only way those reviewed facts are also deleted.

    Facts belonging to other resumes are never queried for deletion.
    Jobs, preferences, and saved jobs have no FK to resumes and are
    untouched. Returns `(facts_deleted, facts_preserved, primary_resume_id)`.
    """
    resume = get_resume_or_404(db, candidate, resume_id)
    others = [
        row
        for row in db.execute(select(Resume).where(Resume.candidate_id == candidate.id)).scalars().all()
        if row.id != resume.id
    ]

    new_primary_id: int | None = None
    if resume.is_primary:
        if others:
            if replacement_resume_id is None:
                raise ConflictError(
                    "This is the primary resume. Choose another uploaded resume to become "
                    "primary before deleting it."
                )
            if replacement_resume_id == resume.id:
                raise ConflictError("replacement_resume_id cannot be the resume being deleted.")
            replacement = get_resume_or_404(db, candidate, replacement_resume_id)
            resume.is_primary = False
            db.flush()
            replacement.is_primary = True
            new_primary_id = replacement.id
    else:
        current_primary = next((row for row in others if row.is_primary), None)
        new_primary_id = current_primary.id if current_primary is not None else None

    facts = list_facts_for_resume(db, candidate, resume_id)
    facts_deleted = 0
    facts_preserved = 0
    for fact in facts:
        keep_independently = fact.verification_status in _INDEPENDENT_FACT_STATUSES
        if keep_independently and not delete_verified_facts:
            fact.resume_id = None
            facts_preserved += 1
        else:
            db.delete(fact)
            facts_deleted += 1
    db.flush()

    checksum = resume.sha256_checksum
    storage_path = Path(resume.storage_path)
    db.delete(resume)
    db.flush()

    still_referenced = db.execute(
        select(Resume.id).where(Resume.sha256_checksum == checksum).limit(1)
    ).first()
    db.commit()

    if still_referenced is None and storage_path.is_file():
        storage_path.unlink(missing_ok=True)

    return facts_deleted, facts_preserved, new_primary_id
