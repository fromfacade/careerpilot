"""Canonical knowledge-base mutations.

Extracted `candidate_facts` are never modified here. This service only
creates, updates, archives, or deletes `canonical_facts` and their
provenance links. Resume deletion is handled by `resume_service` and cannot
cascade onto these rows (see the SET NULL FKs on `canonical_fact_sources`).

Import is explicit: verifying a resume fact does not promote it. Exact
content matches are skipped (a provenance link is added if missing).
Same-identity different content becomes a `conflict` row. The active value
is never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact, CanonicalFactSource
from app.models.enums import (
    CanonicalFactOrigin,
    CanonicalFactStatus,
    FactType,
    FactVerificationStatus,
)
from app.models.resume import CandidateFact
from app.resume_parsing.dedupe import content_fingerprint, identity_key_string

_IMPORTABLE = frozenset({FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED})
_REVIEW_KEYS = frozenset({"needs_review", "review_reasons", "ambiguous_fields", "unclassified_text", "possible_duplicate_of"})


@dataclass(frozen=True)
class ImportDecision:
    action: Literal["create", "link_source", "conflict", "skip"]
    reason: str
    existing_id: int | None = None


@dataclass
class ImportOutcome:
    created: int = 0
    linked: int = 0
    conflicts: int = 0
    skipped: int = 0
    facts: list[CanonicalFact] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload(fact_value: dict) -> dict:
    """Copy `fact_value` without parser-authored review metadata."""
    return {k: v for k, v in (fact_value or {}).items() if k not in _REVIEW_KEYS}


def decide_import(
    *,
    extracted_id: int,
    identity: str,
    fingerprint: str,
    active_by_identity: dict[str, int],
    active_by_fingerprint: dict[str, int],
    already_linked: set[int],
    known_conflict_fingerprints: set[str],
) -> ImportDecision:
    """Pure import rule. Never mutates; the service applies the decision."""
    if extracted_id in already_linked:
        return ImportDecision("skip", "Already imported.", existing_id=None)
    if fingerprint in known_conflict_fingerprints:
        return ImportDecision("skip", "This conflicting version is already recorded.")
    match_fp = active_by_fingerprint.get(fingerprint)
    if match_fp is not None:
        return ImportDecision("link_source", "Identical to an active canonical fact.", existing_id=match_fp)
    match_id = active_by_identity.get(identity)
    if match_id is not None:
        return ImportDecision(
            "conflict",
            f"Same name as canonical fact #{match_id} but different content. The active record was not changed.",
            existing_id=match_id,
        )
    return ImportDecision("create", "No matching canonical fact.")


def _snapshot(db: Session, candidate: Candidate) -> tuple[dict[str, int], dict[str, int], set[int], set[str]]:
    rows = list(
        db.execute(select(CanonicalFact).where(CanonicalFact.candidate_id == candidate.id)).scalars().all()
    )
    active_by_identity: dict[str, int] = {}
    active_by_fingerprint: dict[str, int] = {}
    conflict_fps: set[str] = set()
    for row in rows:
        if row.status is CanonicalFactStatus.ACTIVE:
            active_by_identity[row.identity_key] = row.id
            active_by_fingerprint[row.content_fingerprint] = row.id
        elif row.status is CanonicalFactStatus.CONFLICT:
            conflict_fps.add(row.content_fingerprint)
    linked = {
        source.candidate_fact_id
        for source in db.execute(
            select(CanonicalFactSource).where(CanonicalFactSource.candidate_fact_id.is_not(None))
        ).scalars().all()
        if source.candidate_fact_id is not None
    }
    return active_by_identity, active_by_fingerprint, linked, conflict_fps


def _add_source(
    db: Session,
    canonical: CanonicalFact,
    extracted: CandidateFact,
    *,
    origin: CanonicalFactOrigin = CanonicalFactOrigin.RESUME_IMPORT,
    note: str | None = None,
) -> None:
    existing = db.execute(
        select(CanonicalFactSource).where(CanonicalFactSource.candidate_fact_id == extracted.id)
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        CanonicalFactSource(
            canonical_fact_id=canonical.id,
            candidate_fact_id=extracted.id,
            resume_id=extracted.resume_id,
            origin=origin,
            note=note,
        )
    )


def import_verified_facts(
    db: Session,
    candidate: Candidate,
    fact_ids: list[int] | None = None,
) -> ImportOutcome:
    """Promote verified/edited extracted facts into the knowledge base.

    Unverified and rejected facts are ignored. Existing canonical values are
    never overwritten.
    """
    stmt = select(CandidateFact).where(
        CandidateFact.candidate_id == candidate.id,
        CandidateFact.verification_status.in_(_IMPORTABLE),
    )
    if fact_ids is not None:
        if not fact_ids:
            return ImportOutcome()
        stmt = stmt.where(CandidateFact.id.in_(fact_ids))
    extracted_rows = list(db.execute(stmt).scalars().all())
    if fact_ids is not None:
        found = {row.id for row in extracted_rows}
        missing = [fid for fid in fact_ids if fid not in found]
        if missing:
            raise NotFoundError(
                f"Facts {missing} are missing, not this candidate's, or not verified/edited."
            )

    outcome = ImportOutcome()
    for extracted in extracted_rows:
        identity = identity_key_string(extracted.fact_type, extracted.fact_key)
        fingerprint = content_fingerprint(extracted.fact_type, extracted.fact_key, extracted.fact_value)
        active_by_identity, active_by_fingerprint, linked, conflict_fps = _snapshot(db, candidate)
        decision = decide_import(
            extracted_id=extracted.id,
            identity=identity,
            fingerprint=fingerprint,
            active_by_identity=active_by_identity,
            active_by_fingerprint=active_by_fingerprint,
            already_linked=linked,
            known_conflict_fingerprints=conflict_fps,
        )
        if decision.action == "skip":
            outcome.skipped += 1
            continue
        if decision.action == "link_source":
            existing = db.get(CanonicalFact, decision.existing_id)
            assert existing is not None
            _add_source(db, existing, extracted, note="Identical to the active canonical fact.")
            outcome.linked += 1
            outcome.facts.append(existing)
            continue
        if decision.action == "conflict":
            row = CanonicalFact(
                candidate_id=candidate.id,
                fact_type=extracted.fact_type,
                fact_key=extracted.fact_key,
                fact_value=_payload(extracted.fact_value),
                identity_key=identity,
                content_fingerprint=fingerprint,
                status=CanonicalFactStatus.CONFLICT,
                verification_status=FactVerificationStatus.UNVERIFIED,
                needs_review=True,
                review_reasons=[decision.reason],
                conflicts_with_id=decision.existing_id,
            )
            db.add(row)
            db.flush()
            _add_source(db, row, extracted, note=decision.reason)
            outcome.conflicts += 1
            outcome.facts.append(row)
            continue
        row = CanonicalFact(
            candidate_id=candidate.id,
            fact_type=extracted.fact_type,
            fact_key=extracted.fact_key,
            fact_value=_payload(extracted.fact_value),
            identity_key=identity,
            content_fingerprint=fingerprint,
            status=CanonicalFactStatus.ACTIVE,
            verification_status=extracted.verification_status,
            verified_at=extracted.verified_at,
            needs_review=False,
            review_reasons=[],
        )
        db.add(row)
        db.flush()
        _add_source(db, row, extracted)
        outcome.created += 1
        outcome.facts.append(row)

    db.commit()
    for fact in outcome.facts:
        db.refresh(fact)
    return outcome


def list_canonical_facts(
    db: Session,
    candidate: Candidate,
    *,
    fact_type: FactType | None = None,
    status: CanonicalFactStatus | None = None,
    verification_status: FactVerificationStatus | None = None,
) -> list[CanonicalFact]:
    stmt = select(CanonicalFact).where(CanonicalFact.candidate_id == candidate.id)
    if fact_type is not None:
        stmt = stmt.where(CanonicalFact.fact_type == fact_type)
    if status is not None:
        stmt = stmt.where(CanonicalFact.status == status)
    if verification_status is not None:
        stmt = stmt.where(CanonicalFact.verification_status == verification_status)
    stmt = stmt.order_by(CanonicalFact.fact_type, CanonicalFact.id)
    return list(db.execute(stmt).scalars().all())


def get_canonical_fact_or_404(db: Session, candidate: Candidate, fact_id: int) -> CanonicalFact:
    fact = db.get(CanonicalFact, fact_id)
    if fact is None or fact.candidate_id != candidate.id:
        raise NotFoundError(f"No canonical fact with id={fact_id} for this candidate.")
    return fact


def create_manual_fact(
    db: Session,
    candidate: Candidate,
    *,
    fact_type: FactType,
    fact_key: str,
    fact_value: dict,
) -> CanonicalFact:
    """Add a knowledge-base fact by hand. Starts unverified. Never invents fields."""
    identity = identity_key_string(fact_type, fact_key)
    fingerprint = content_fingerprint(fact_type, fact_key, fact_value)
    clash = db.execute(
        select(CanonicalFact.id).where(
            CanonicalFact.candidate_id == candidate.id,
            CanonicalFact.identity_key == identity,
            CanonicalFact.status == CanonicalFactStatus.ACTIVE,
        )
    ).first()
    if clash is not None:
        raise ConflictError(
            f"An active canonical fact already exists for '{fact_key}'. "
            "Edit or archive it; values are never overwritten silently."
        )
    row = CanonicalFact(
        candidate_id=candidate.id,
        fact_type=fact_type,
        fact_key=fact_key,
        fact_value=_payload(fact_value),
        identity_key=identity,
        content_fingerprint=fingerprint,
        status=CanonicalFactStatus.ACTIVE,
        verification_status=FactVerificationStatus.UNVERIFIED,
        needs_review=False,
        review_reasons=[],
    )
    db.add(row)
    db.flush()
    db.add(
        CanonicalFactSource(
            canonical_fact_id=row.id,
            origin=CanonicalFactOrigin.MANUAL_ENTRY,
            note="Entered manually.",
        )
    )
    db.commit()
    db.refresh(row)
    return row


def update_canonical_fact(
    db: Session,
    candidate: Candidate,
    fact_id: int,
    *,
    fact_key: str | None = None,
    fact_value: dict | None = None,
    verification_status: FactVerificationStatus | None = None,
) -> CanonicalFact:
    fact = get_canonical_fact_or_404(db, candidate, fact_id)
    if fact.status is CanonicalFactStatus.ARCHIVED:
        raise ValidationError("Archived facts cannot be edited. Restore is not automatic; add a new fact.")
    content_changed = False
    if fact_key is not None and fact_key != fact.fact_key:
        fact.fact_key = fact_key
        content_changed = True
    if fact_value is not None:
        fact.fact_value = _payload(fact_value)
        content_changed = True
    if content_changed:
        new_identity = identity_key_string(fact.fact_type, fact.fact_key)
        clash = db.execute(
            select(CanonicalFact.id).where(
                CanonicalFact.candidate_id == candidate.id,
                CanonicalFact.identity_key == new_identity,
                CanonicalFact.status == CanonicalFactStatus.ACTIVE,
                CanonicalFact.id != fact.id,
            )
        ).first()
        if clash is not None and fact.status is CanonicalFactStatus.ACTIVE:
            raise ConflictError(
                f"Another active canonical fact already uses the name '{fact.fact_key}'."
            )
        fact.identity_key = new_identity
        fact.content_fingerprint = content_fingerprint(fact.fact_type, fact.fact_key, fact.fact_value)
    new_status = verification_status
    if new_status is None and content_changed:
        new_status = FactVerificationStatus.EDITED
    if new_status is FactVerificationStatus.UNVERIFIED:
        raise ValidationError("verification_status cannot be set back to unverified.")
    if new_status is FactVerificationStatus.REJECTED:
        raise ValidationError("Reject a canonical fact by archiving or deleting it; rejection is for extracted records.")
    if new_status is not None:
        fact.verification_status = new_status
        fact.verified_at = _now()
        if new_status in {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}:
            fact.needs_review = False
    db.commit()
    db.refresh(fact)
    return fact


def archive_canonical_fact(db: Session, candidate: Candidate, fact_id: int) -> CanonicalFact:
    fact = get_canonical_fact_or_404(db, candidate, fact_id)
    fact.status = CanonicalFactStatus.ARCHIVED
    fact.archived_at = _now()
    db.commit()
    db.refresh(fact)
    return fact


def delete_canonical_fact(db: Session, candidate: Candidate, fact_id: int) -> None:
    """Remove a canonical row only. Extracted records are not touched."""
    fact = get_canonical_fact_or_404(db, candidate, fact_id)
    db.delete(fact)
    db.commit()


def resolve_conflict(
    db: Session,
    candidate: Candidate,
    conflict_id: int,
    *,
    keep: Literal["existing", "incoming"],
) -> CanonicalFact:
    """Human resolution of a same-identity conflict. Never automatic."""
    incoming = get_canonical_fact_or_404(db, candidate, conflict_id)
    if incoming.status is not CanonicalFactStatus.CONFLICT or incoming.conflicts_with_id is None:
        raise ValidationError("That record is not an unresolved conflict.")
    existing = get_canonical_fact_or_404(db, candidate, incoming.conflicts_with_id)
    if keep == "existing":
        incoming.status = CanonicalFactStatus.ARCHIVED
        incoming.archived_at = _now()
        incoming.needs_review = False
        db.commit()
        db.refresh(existing)
        return existing
    if existing.status is CanonicalFactStatus.ACTIVE:
        existing.status = CanonicalFactStatus.ARCHIVED
        existing.archived_at = _now()
        db.flush()
    incoming.status = CanonicalFactStatus.ACTIVE
    incoming.conflicts_with_id = None
    incoming.needs_review = False
    incoming.review_reasons = []
    incoming.verification_status = FactVerificationStatus.VERIFIED
    incoming.verified_at = _now()
    db.commit()
    db.refresh(incoming)
    return incoming
