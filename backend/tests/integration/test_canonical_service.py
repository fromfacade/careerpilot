"""Service-level tests for canonical import, conflicts, and isolation.

Goes through `canonical_service` against the real test database. No HTTP yet.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from sqlalchemy import select

from app.models.canonical import CanonicalFact, CanonicalFactSource
from app.models.candidate import Candidate
from app.models.enums import (
    CanonicalFactStatus,
    FactSource,
    FactType,
    FactVerificationStatus,
    ResumeFileFormat,
    ResumeParseStatus,
)
from app.models.resume import CandidateFact, Resume
from app.services import canonical_service


def _candidate(db) -> Candidate:
    row = Candidate(full_name="Jane Doe", email="jane.canon@example.com")
    db.add(row)
    db.flush()
    return row


def _resume(db, candidate: Candidate, name="v1.pdf") -> Resume:
    row = Resume(
        candidate_id=candidate.id,
        original_filename=name,
        file_format=ResumeFileFormat.PDF,
        storage_path=f"/tmp/{name}",
        file_size_bytes=10,
        sha256_checksum=f"sum-{name}",
        parse_status=ResumeParseStatus.SUCCESS,
    )
    db.add(row)
    db.flush()
    return row


def _fact(
    db,
    candidate: Candidate,
    resume: Resume | None,
    *,
    key: str,
    value: dict,
    status: FactVerificationStatus = FactVerificationStatus.VERIFIED,
    fact_type: FactType = FactType.PROJECT,
) -> CandidateFact:
    row = CandidateFact(
        candidate_id=candidate.id,
        resume_id=resume.id if resume else None,
        fact_type=fact_type,
        fact_key=key,
        fact_value=value,
        source=FactSource.RESUME_EXTRACTION,
        verification_status=status,
        verified_at=datetime.now(timezone.utc) if status != FactVerificationStatus.UNVERIFIED else None,
    )
    db.add(row)
    db.flush()
    return row


def test_import_creates_one_canonical_row_per_verified_fact(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    _fact(db_session, candidate, resume, key="Alpha", value={"name": "Alpha", "bullets": ["Built it."]})
    _fact(db_session, candidate, resume, key="Beta", value={"name": "Beta", "bullets": ["Shipped it."]})
    unverified = _fact(
        db_session,
        candidate,
        resume,
        key="Gamma",
        value={"name": "Gamma"},
        status=FactVerificationStatus.UNVERIFIED,
    )

    outcome = canonical_service.import_verified_facts(db_session, candidate)
    assert (outcome.created, outcome.linked, outcome.conflicts, outcome.skipped) == (2, 0, 0, 0)
    rows = canonical_service.list_canonical_facts(db_session, candidate)
    assert {r.fact_key for r in rows} == {"Alpha", "Beta"}
    assert all(r.status is CanonicalFactStatus.ACTIVE for r in rows)
    assert all(r.verification_status is FactVerificationStatus.VERIFIED for r in rows)
    assert db_session.get(CandidateFact, unverified.id).verification_status is FactVerificationStatus.UNVERIFIED


def test_second_resume_with_the_same_content_links_and_does_not_duplicate(db_session):
    candidate = _candidate(db_session)
    first = _resume(db_session, candidate, "v1.pdf")
    payload = {"name": "Alpha", "bullets": ["Built it."]}
    _fact(db_session, candidate, first, key="Alpha", value=payload)
    canonical_service.import_verified_facts(db_session, candidate)

    second = _resume(db_session, candidate, "v2.pdf")
    _fact(db_session, candidate, second, key="Alpha", value=payload)
    outcome = canonical_service.import_verified_facts(db_session, candidate)
    assert outcome.created == 0 and outcome.linked == 1 and outcome.conflicts == 0

    actives = canonical_service.list_canonical_facts(
        db_session, candidate, status=CanonicalFactStatus.ACTIVE
    )
    assert len(actives) == 1
    sources = list(
        db_session.execute(
            select(CanonicalFactSource).where(CanonicalFactSource.canonical_fact_id == actives[0].id)
        ).scalars().all()
    )
    assert len(sources) == 2
    assert {s.resume_id for s in sources} == {first.id, second.id}


def test_conflicting_content_is_recorded_and_does_not_overwrite(db_session):
    candidate = _candidate(db_session)
    first = _resume(db_session, candidate, "v1.pdf")
    original = _fact(
        db_session, candidate, first, key="Alpha", value={"name": "Alpha", "bullets": ["Built it."]}
    )
    canonical_service.import_verified_facts(db_session, candidate)
    active = canonical_service.list_canonical_facts(db_session, candidate)[0]
    original_value = dict(active.fact_value)

    second = _resume(db_session, candidate, "v2.pdf")
    _fact(
        db_session,
        candidate,
        second,
        key="Alpha",
        value={"name": "Alpha", "bullets": ["Built it.", "Added caching."]},
    )
    outcome = canonical_service.import_verified_facts(db_session, candidate)
    assert outcome.conflicts == 1 and outcome.created == 0

    db_session.refresh(active)
    assert active.fact_value == original_value
    assert active.verification_status is FactVerificationStatus.VERIFIED

    conflicts = canonical_service.list_canonical_facts(
        db_session, candidate, status=CanonicalFactStatus.CONFLICT
    )
    assert len(conflicts) == 1
    assert conflicts[0].conflicts_with_id == active.id
    assert conflicts[0].needs_review is True
    assert "Added caching." in conflicts[0].fact_value["bullets"]
    assert db_session.get(CandidateFact, original.id).fact_value == {"name": "Alpha", "bullets": ["Built it."]}


def test_resolving_a_conflict_in_favor_of_incoming_archives_the_old_active(db_session):
    candidate = _candidate(db_session)
    v1 = _resume(db_session, candidate, "v1.pdf")
    _fact(db_session, candidate, v1, key="Alpha", value={"name": "Alpha", "bullets": ["One."]})
    canonical_service.import_verified_facts(db_session, candidate)
    v2 = _resume(db_session, candidate, "v2.pdf")
    _fact(db_session, candidate, v2, key="Alpha", value={"name": "Alpha", "bullets": ["One.", "Two."]})
    conflict = canonical_service.import_verified_facts(db_session, candidate).facts[0]

    winner = canonical_service.resolve_conflict(db_session, candidate, conflict.id, keep="incoming")
    assert winner.id == conflict.id
    assert winner.status is CanonicalFactStatus.ACTIVE
    assert winner.verification_status is FactVerificationStatus.VERIFIED
    assert winner.fact_value["bullets"] == ["One.", "Two."]

    archived = [
        r
        for r in canonical_service.list_canonical_facts(db_session, candidate)
        if r.status is CanonicalFactStatus.ARCHIVED
    ]
    assert len(archived) == 1
    assert archived[0].fact_value["bullets"] == ["One."]


def test_resolving_a_conflict_in_favor_of_existing_keeps_the_active_value(db_session):
    candidate = _candidate(db_session)
    v1 = _resume(db_session, candidate, "v1.pdf")
    _fact(db_session, candidate, v1, key="Alpha", value={"name": "Alpha", "bullets": ["One."]})
    canonical_service.import_verified_facts(db_session, candidate)
    v2 = _resume(db_session, candidate, "v2.pdf")
    _fact(db_session, candidate, v2, key="Alpha", value={"name": "Alpha", "bullets": ["Changed."]})
    conflict = canonical_service.import_verified_facts(db_session, candidate).facts[0]
    kept = canonical_service.resolve_conflict(db_session, candidate, conflict.id, keep="existing")
    assert kept.fact_value["bullets"] == ["One."]
    assert kept.status is CanonicalFactStatus.ACTIVE
    db_session.refresh(conflict)
    assert conflict.status is CanonicalFactStatus.ARCHIVED


def test_unverified_and_rejected_facts_are_not_imported(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    unverified = _fact(
        db_session, candidate, resume, key="A", value={"name": "A"}, status=FactVerificationStatus.UNVERIFIED
    )
    rejected = _fact(
        db_session, candidate, resume, key="B", value={"name": "B"}, status=FactVerificationStatus.REJECTED
    )
    with pytest.raises(NotFoundError):
        canonical_service.import_verified_facts(db_session, candidate, fact_ids=[unverified.id, rejected.id])
    assert canonical_service.list_canonical_facts(db_session, candidate) == []


def test_manual_create_starts_unverified_and_refuses_a_duplicate_identity(db_session):
    candidate = _candidate(db_session)
    created = canonical_service.create_manual_fact(
        db_session,
        candidate,
        fact_type=FactType.SKILL,
        fact_key="Languages",
        fact_value={"items": ["English", "Spanish"]},
    )
    assert created.verification_status is FactVerificationStatus.UNVERIFIED
    assert created.sources[0].origin.value == "manual_entry"
    with pytest.raises(ConflictError):
        canonical_service.create_manual_fact(
            db_session,
            candidate,
            fact_type=FactType.SKILL,
            fact_key="languages",
            fact_value={"items": ["French"]},
        )


def test_editing_does_not_invent_and_delete_leaves_extracted_facts(db_session):
    candidate = _candidate(db_session)
    resume = _resume(db_session, candidate)
    extracted = _fact(db_session, candidate, resume, key="Alpha", value={"name": "Alpha", "bullets": ["One."]})
    imported = canonical_service.import_verified_facts(db_session, candidate).facts[0]
    extracted_id = extracted.id

    updated = canonical_service.update_canonical_fact(
        db_session,
        candidate,
        imported.id,
        fact_value={"name": "Alpha", "tagline": "Scheduler", "bullets": ["One."]},
    )
    assert updated.verification_status is FactVerificationStatus.EDITED
    assert updated.fact_value["tagline"] == "Scheduler"
    assert "gpa" not in updated.fact_value

    canonical_service.delete_canonical_fact(db_session, candidate, imported.id)
    assert db_session.get(CanonicalFact, imported.id) is None
    leftover = db_session.get(CandidateFact, extracted_id)
    assert leftover is not None
    assert leftover.fact_key == "Alpha"
    assert leftover.verification_status is FactVerificationStatus.VERIFIED


def test_archive_frees_the_identity_for_a_new_manual_fact(db_session):
    candidate = _candidate(db_session)
    first = canonical_service.create_manual_fact(
        db_session, candidate, fact_type=FactType.EDUCATION, fact_key="Example U", fact_value={"institution": "Example U"}
    )
    canonical_service.archive_canonical_fact(db_session, candidate, first.id)
    second = canonical_service.create_manual_fact(
        db_session,
        candidate,
        fact_type=FactType.EDUCATION,
        fact_key="Example U",
        fact_value={"institution": "Example U", "degree": "B.S."},
    )
    assert second.id != first.id
    assert second.status is CanonicalFactStatus.ACTIVE


def test_cannot_revert_canonical_verification_to_unverified(db_session):
    candidate = _candidate(db_session)
    row = canonical_service.create_manual_fact(
        db_session, candidate, fact_type=FactType.OTHER, fact_key="Note", fact_value={"text": "hello"}
    )
    canonical_service.update_canonical_fact(
        db_session, candidate, row.id, verification_status=FactVerificationStatus.VERIFIED
    )
    with pytest.raises(ValidationError):
        canonical_service.update_canonical_fact(
            db_session, candidate, row.id, verification_status=FactVerificationStatus.UNVERIFIED
        )
