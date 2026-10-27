"""Pure import-rule tests (no database)."""

from app.resume_parsing.dedupe import identity_key_string
from app.models.enums import FactType
from app.services.canonical_service import decide_import


def test_identity_key_string_normalizes_case_and_space():
    assert identity_key_string(FactType.PROJECT, " Alpha  Queue ") == "project|alpha queue"


def test_already_linked_extracted_fact_is_skipped():
    decision = decide_import(
        extracted_id=9,
        identity="project|alpha",
        fingerprint="fp-a",
        active_by_identity={},
        active_by_fingerprint={},
        already_linked={9},
        known_conflict_fingerprints=set(),
    )
    assert decision.action == "skip"


def test_identical_content_links_to_the_active_fact():
    decision = decide_import(
        extracted_id=1,
        identity="project|alpha",
        fingerprint="fp-a",
        active_by_identity={"project|alpha": 4},
        active_by_fingerprint={"fp-a": 4},
        already_linked=set(),
        known_conflict_fingerprints=set(),
    )
    assert decision.action == "link_source" and decision.existing_id == 4


def test_same_identity_different_content_is_a_conflict():
    decision = decide_import(
        extracted_id=1,
        identity="project|alpha",
        fingerprint="fp-new",
        active_by_identity={"project|alpha": 4},
        active_by_fingerprint={"fp-old": 4},
        already_linked=set(),
        known_conflict_fingerprints=set(),
    )
    assert decision.action == "conflict" and decision.existing_id == 4
    assert "not changed" in decision.reason


def test_an_already_recorded_conflict_is_skipped():
    decision = decide_import(
        extracted_id=2,
        identity="project|alpha",
        fingerprint="fp-new",
        active_by_identity={"project|alpha": 4},
        active_by_fingerprint={"fp-old": 4},
        already_linked=set(),
        known_conflict_fingerprints={"fp-new"},
    )
    assert decision.action == "skip"


def test_unseen_fact_is_created():
    decision = decide_import(
        extracted_id=1,
        identity="project|beta",
        fingerprint="fp-b",
        active_by_identity={"project|alpha": 4},
        active_by_fingerprint={"fp-a": 4},
        already_linked=set(),
        known_conflict_fingerprints=set(),
    )
    assert decision.action == "create"
