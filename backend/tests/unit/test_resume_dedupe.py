"""Unit tests for app.resume_parsing.dedupe (pure; no database)."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import FactType
from app.resume_parsing.dedupe import content_fingerprint, identity_key, partition_extracted
from app.resume_parsing.types import ExtractedFact


@dataclass
class _Ref:
    id: int
    fact_type: FactType
    fact_key: str
    fact_value: dict


def _project(name="Alpha", bullets=None, **extra) -> ExtractedFact:
    value = {"name": name, "technologies": ["Python"], "bullets": bullets or ["Built a thing."], **extra}
    return ExtractedFact(fact_type=FactType.PROJECT, fact_key=name, fact_value=value, raw_text=name)


def _ref(fact: ExtractedFact, fact_id: int = 1) -> _Ref:
    return _Ref(fact_id, fact.fact_type, fact.fact_key, dict(fact.fact_value))


def test_fingerprint_ignores_case_whitespace_and_review_metadata():
    a = content_fingerprint(FactType.PROJECT, "Alpha  Queue", {"name": "Alpha Queue", "needs_review": True})
    b = content_fingerprint(FactType.PROJECT, "alpha queue", {"name": "alpha   queue", "review_reasons": ["x"]})
    assert a == b


def test_fingerprint_distinguishes_different_content_and_types():
    base = content_fingerprint(FactType.PROJECT, "Alpha", {"bullets": ["one"]})
    assert base != content_fingerprint(FactType.PROJECT, "Alpha", {"bullets": ["one", "two"]})
    assert base != content_fingerprint(FactType.WORK_EXPERIENCE, "Alpha", {"bullets": ["one"]})


def test_identity_key_is_type_plus_normalized_key():
    assert identity_key(FactType.PROJECT, " Alpha  Queue ") == ("project", "alpha queue")


def test_identical_to_a_reviewed_fact_is_skipped():
    existing = _project()
    result = partition_extracted([_project(), _project("Beta")], reviewed=[_ref(existing)])
    assert [f.fact_key for f in result.to_create] == ["Beta"]
    assert result.skipped_duplicates == 1
    assert result.flagged_conflicts == 0


def test_same_name_but_different_content_is_kept_and_flagged_for_review():
    existing = _project(bullets=["Built a thing."])
    updated = _project(bullets=["Built a thing.", "Added caching."])
    result = partition_extracted([updated], reviewed=[_ref(existing, fact_id=42)])
    assert result.skipped_duplicates == 0
    assert result.flagged_conflicts == 1
    (kept,) = result.to_create
    assert kept.fact_value["needs_review"] is True
    assert kept.fact_value["possible_duplicate_of"] == 42
    assert any("#42" in reason for reason in kept.fact_value["review_reasons"])
    # The incoming content itself is untouched.
    assert kept.fact_value["bullets"] == ["Built a thing.", "Added caching."]


def test_identical_facts_within_one_parse_collapse_to_one():
    result = partition_extracted([_project(), _project()], reviewed=[])
    assert len(result.to_create) == 1 and result.skipped_duplicates == 1


def test_suppressed_content_does_not_come_back_but_other_facts_do():
    rejected = _project("Gone")
    result = partition_extracted([_project("Gone"), _project("Keep")], reviewed=[], suppress=[_ref(rejected)])
    assert [f.fact_key for f in result.to_create] == ["Keep"]
    assert result.skipped_duplicates == 1


def test_nothing_is_skipped_across_fact_types():
    work = ExtractedFact(FactType.WORK_EXPERIENCE, "Alpha", {"name": "Alpha"}, "Alpha")
    result = partition_extracted([_project("Alpha")], reviewed=[_ref(work)])
    assert len(result.to_create) == 1 and result.skipped_duplicates == 0
