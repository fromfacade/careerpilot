"""Schema-level tests for the canonical knowledge-base tables.

No API yet — this increment only adds the tables. These tests prove the
constraints that later increments rely on: one active identity, provenance
that survives resume/extracted-fact deletion, and no cascade from resumes
onto canonical rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.canonical import CanonicalFact, CanonicalFactSource
from app.models.candidate import Candidate
from app.models.enums import (
    CanonicalFactOrigin,
    CanonicalFactStatus,
    FactSource,
    FactType,
    FactVerificationStatus,
    ResumeFileFormat,
    ResumeParseStatus,
)
from app.models.resume import CandidateFact, Resume


def _candidate(db_session) -> Candidate:
    row = Candidate(full_name="Jane Doe", email="jane.schema@example.com")
    db_session.add(row)
    db_session.flush()
    return row


def _resume(db_session, candidate: Candidate) -> Resume:
    row = Resume(
        candidate_id=candidate.id,
        original_filename="resume.pdf",
        file_format=ResumeFileFormat.PDF,
        storage_path="/tmp/does-not-need-to-exist.pdf",
        file_size_bytes=12,
        sha256_checksum="schema-test-checksum",
        parse_status=ResumeParseStatus.SUCCESS,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _extracted(db_session, candidate: Candidate, resume: Resume, key="Northwind") -> CandidateFact:
    row = CandidateFact(
        candidate_id=candidate.id,
        resume_id=resume.id,
        fact_type=FactType.WORK_EXPERIENCE,
        fact_key=key,
        fact_value={"employer": key, "position": "Analyst"},
        source=FactSource.RESUME_EXTRACTION,
        verification_status=FactVerificationStatus.VERIFIED,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _canonical(db_session, candidate: Candidate, *, key="Northwind", status=CanonicalFactStatus.ACTIVE) -> CanonicalFact:
    row = CanonicalFact(
        candidate_id=candidate.id,
        fact_type=FactType.WORK_EXPERIENCE,
        fact_key=key,
        fact_value={"employer": key, "position": "Analyst"},
        identity_key=f"work_experience|{key.casefold()}",
        content_fingerprint=f"fp-{key.casefold()}",
        status=status,
        verification_status=FactVerificationStatus.VERIFIED,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_two_active_facts_cannot_share_an_identity(db_session):
    candidate = _candidate(db_session)
    _canonical(db_session, candidate)
    with pytest.raises(IntegrityError):
        _canonical(db_session, candidate)


def test_a_conflict_row_may_reuse_the_active_identity(db_session):
    candidate = _candidate(db_session)
    active = _canonical(db_session, candidate)
    conflict = CanonicalFact(
        candidate_id=candidate.id,
        fact_type=FactType.WORK_EXPERIENCE,
        fact_key="Northwind",
        fact_value={"employer": "Northwind", "position": "Senior Analyst"},
        identity_key=active.identity_key,
        content_fingerprint="fp-northwind-senior",
        status=CanonicalFactStatus.CONFLICT,
        conflicts_with_id=active.id,
        needs_review=True,
        review_reasons=["Same employer, different position."],
        verification_status=FactVerificationStatus.UNVERIFIED,
    )
    db_session.add(conflict)
    db_session.flush()
    assert conflict.conflicts_with_id == active.id
    assert conflict.status is CanonicalFactStatus.CONFLICT


def test_deleting_a_resume_does_not_delete_the_canonical_fact(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    extracted = _extracted(db_session, candidate, resume)
    canonical = _canonical(db_session, candidate)
    source = CanonicalFactSource(
        canonical_fact_id=canonical.id,
        candidate_fact_id=extracted.id,
        resume_id=resume.id,
        origin=CanonicalFactOrigin.RESUME_IMPORT,
        note="Imported from verified resume fact",
    )
    db_session.add(source)
    db_session.flush()

    db_session.delete(resume)
    db_session.flush()

    db_session.refresh(canonical)
    db_session.refresh(source)
    db_session.refresh(extracted)
    assert db_session.get(CanonicalFact, canonical.id) is not None
    # The extracted record is preserved (resume_id SET NULL); only the
    # provenance's resume pointer is cleared. Canonical content is untouched.
    assert extracted.resume_id is None
    assert source.resume_id is None
    assert source.candidate_fact_id == extracted.id
    assert source.origin is CanonicalFactOrigin.RESUME_IMPORT


def test_deleting_an_extracted_fact_leaves_canonical_and_clears_the_link(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    extracted = _extracted(db_session, candidate, resume)
    canonical = _canonical(db_session, candidate)
    source = CanonicalFactSource(
        canonical_fact_id=canonical.id,
        candidate_fact_id=extracted.id,
        resume_id=resume.id,
        origin=CanonicalFactOrigin.RESUME_IMPORT,
    )
    db_session.add(source)
    db_session.flush()

    db_session.delete(extracted)
    db_session.flush()

    assert db_session.get(CanonicalFact, canonical.id) is not None
    db_session.refresh(source)
    assert source.candidate_fact_id is None
    assert source.resume_id == resume.id


def test_one_extracted_fact_links_to_at_most_one_canonical_row(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    extracted = _extracted(db_session, candidate, resume)
    first = _canonical(db_session, candidate, key="Northwind")
    second = _canonical(db_session, candidate, key="Contoso")
    db_session.add(
        CanonicalFactSource(
            canonical_fact_id=first.id,
            candidate_fact_id=extracted.id,
            resume_id=resume.id,
            origin=CanonicalFactOrigin.RESUME_IMPORT,
        )
    )
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(
            CanonicalFactSource(
                canonical_fact_id=second.id,
                candidate_fact_id=extracted.id,
                resume_id=resume.id,
                origin=CanonicalFactOrigin.RESUME_IMPORT,
            )
        )
        db_session.flush()
