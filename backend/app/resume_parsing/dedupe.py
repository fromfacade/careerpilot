"""Duplicate detection between freshly extracted facts and existing records.

Pure functions (no database access) so the rules are unit-testable. The
service layer supplies the reference facts and decides what to persist.

Rules, in order of safety:

* An extracted fact whose *content* matches an existing VERIFIED / EDITED
  fact of the same type is skipped. The reviewed record already represents
  it; inserting another unverified copy would just create review work.
* An extracted fact with the same *identity* (type + key) as a reviewed
  fact but different content is kept -- never silently dropped or
  overwritten -- and flagged for review so the human compares the two.
* Identical facts within a single parse are collapsed to one.

Reviewed facts are never modified here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from app.models.enums import FactType
from app.resume_parsing.types import ExtractedFact

# Parser-authored review metadata. It describes parsing confidence, not the
# content of the record, so it must not influence whether two records match.
_REVIEW_KEYS = frozenset({"needs_review", "review_reasons", "ambiguous_fields", "unclassified_text"})
_WS_RE = re.compile(r"\s+")


class _ReferenceFact(Protocol):
    id: int
    fact_type: FactType
    fact_key: str
    fact_value: dict


def normalize_text(value: str) -> str:
    return _WS_RE.sub(" ", value).strip().casefold()


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items()) if k not in _REVIEW_KEYS}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def content_fingerprint(fact_type: FactType, fact_key: str, fact_value: dict) -> str:
    payload = {"type": fact_type.value, "key": normalize_text(fact_key), "value": _canonical(fact_value)}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def identity_key(fact_type: FactType, fact_key: str) -> tuple[str, str]:
    return fact_type.value, normalize_text(fact_key)


@dataclass
class DedupeResult:
    to_create: list[ExtractedFact]
    skipped_duplicates: int
    flagged_conflicts: int


def partition_extracted(
    extracted: Iterable[ExtractedFact],
    *,
    reviewed: Iterable[_ReferenceFact],
    suppress: Iterable[_ReferenceFact] = (),
) -> DedupeResult:
    """Split `extracted` into facts to insert and duplicates to skip.

    `reviewed`: existing verified/edited facts. Content matches are skipped;
    same-identity-different-content facts are flagged.
    `suppress`: existing facts whose exact content must not come back (for
    example facts the user already rejected in this same resume).
    """
    reviewed_list = list(reviewed)
    reviewed_content = {content_fingerprint(f.fact_type, f.fact_key, f.fact_value) for f in reviewed_list}
    reviewed_by_identity: dict[tuple[str, str], _ReferenceFact] = {}
    for fact in reviewed_list:
        reviewed_by_identity.setdefault(identity_key(fact.fact_type, fact.fact_key), fact)
    suppressed_content = {content_fingerprint(f.fact_type, f.fact_key, f.fact_value) for f in suppress}

    seen: set[str] = set()
    to_create: list[ExtractedFact] = []
    skipped = 0
    flagged = 0
    for fact in extracted:
        fingerprint = content_fingerprint(fact.fact_type, fact.fact_key, fact.fact_value)
        if fingerprint in seen or fingerprint in reviewed_content or fingerprint in suppressed_content:
            skipped += 1
            continue
        seen.add(fingerprint)

        match = reviewed_by_identity.get(identity_key(fact.fact_type, fact.fact_key))
        if match is not None:
            reasons = list(fact.fact_value.get("review_reasons") or [])
            reasons.append(
                f"Differs from the reviewed record #{match.id} with the same name. "
                "Compare them before verifying; the reviewed record was not changed."
            )
            fact.fact_value = {
                **fact.fact_value,
                "needs_review": True,
                "review_reasons": reasons,
                "possible_duplicate_of": match.id,
            }
            flagged += 1
        to_create.append(fact)
    return DedupeResult(to_create=to_create, skipped_duplicates=skipped, flagged_conflicts=flagged)
