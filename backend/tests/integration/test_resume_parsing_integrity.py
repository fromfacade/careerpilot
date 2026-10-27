"""End-to-end resume parsing + data-integrity tests through the real API.

Files are real generated PDFs/DOCX (tests/resume_fixtures.py) uploaded via
`POST /api/resumes`, so upload -> extraction -> parsing -> persistence ->
review are exercised together against the real test database.
"""

from __future__ import annotations

from collections import Counter

import pytest
import resume_fixtures as rf
from resume_fixtures import Section, b, t

from app.core.config import get_settings

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture()
def isolated_resume_settings(tmp_path, monkeypatch):
    overridden = get_settings().model_copy(
        update={"resume_storage_dir": str(tmp_path / "resumes"), "resume_max_upload_mb": 10.0}
    )
    monkeypatch.setattr("app.api.resumes.get_settings", lambda: overridden)
    return overridden


@pytest.fixture()
def candidate(client, isolated_resume_settings):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.doe@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _upload(client, data: bytes, filename: str):
    content_type = DOCX_TYPE if filename.endswith(".docx") else "application/pdf"
    resp = client.post("/api/resumes", files={"file": (filename, data, content_type)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _facts(client, resume_id: int):
    return client.get(f"/api/resumes/{resume_id}/facts").json()


def _counts(facts) -> dict[str, int]:
    return dict(Counter(f["fact_type"] for f in facts))


def _by_type(facts, fact_type: str):
    return [f for f in facts if f["fact_type"] == fact_type]


def _updated_sections(extra_bullet: str) -> list[Section]:
    """The standard resume where the first project gained one bullet."""
    items = list(rf.PROJECTS.items)
    items.insert(7, b(extra_bullet))  # after Alpha's last bullet, before Beta's title
    return [rf.EDUCATION, rf.SKILLS, Section(rf.PROJECTS.heading, items), rf.EXPERIENCE, rf.ACTIVITIES]


# ---- exact counts through the API -----------------------------------------
@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_upload_produces_exact_structured_records_all_unverified(client, candidate, fmt):
    data = rf.standard_pdf() if fmt == "pdf" else rf.standard_docx()
    upload = _upload(client, data, f"resume.{fmt}")
    facts = _facts(client, upload["resume"]["id"])

    assert _counts(facts) == rf.EXPECTED_COUNTS
    assert upload["facts_extracted"] == sum(rf.EXPECTED_COUNTS.values()) == len(facts)
    assert upload["facts_skipped_duplicate"] == 0 and upload["already_uploaded"] is False
    assert upload["resume"]["parse_status"] == "success"
    # Nothing is ever auto-verified.
    assert {f["verification_status"] for f in facts} == {"unverified"}
    assert {f["source"] for f in facts} == {"resume_extraction"}

    assert [f["fact_value"]["name"] for f in _by_type(facts, "project")] == rf.EXPECTED_PROJECT_NAMES
    assert [f["fact_key"] for f in _by_type(facts, "skill")] == rf.EXPECTED_SKILL_CATEGORIES
    jobs = _by_type(facts, "work_experience")
    assert [(j["fact_value"]["employer"], len(j["fact_value"]["bullets"])) for j in jobs] == [
        ("Northwind Tutoring Services", 3),
        ("Contoso Student Life", 2),
    ]


# ---- isolation between uploads ---------------------------------------------
def test_a_second_upload_is_isolated_from_the_first_resumes_records(client, candidate):
    first = _upload(client, rf.standard_pdf(), "first.pdf")["resume"]
    first_facts_before = _facts(client, first["id"])

    second = _upload(client, rf.standard_docx(), "second.docx")["resume"]
    assert second["id"] != first["id"]

    second_facts = _facts(client, second["id"])
    assert _counts(second_facts) == rf.EXPECTED_COUNTS
    assert {f["resume_id"] for f in second_facts} == {second["id"]}
    assert {f["id"] for f in second_facts}.isdisjoint({f["id"] for f in first_facts_before})

    first_facts_after = _facts(client, first["id"])
    assert first_facts_after == first_facts_before, "uploading another resume must not touch the first"


def test_deleting_one_resume_leaves_the_other_resumes_records_intact(client, candidate):
    first = _upload(client, rf.standard_pdf(), "first.pdf")["resume"]
    second = _upload(client, rf.standard_docx(), "second.docx")["resume"]
    second_before = _facts(client, second["id"])

    resp = client.request("DELETE", f"/api/resumes/{first['id']}", json={"replacement_resume_id": second["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["facts_deleted"] == sum(rf.EXPECTED_COUNTS.values())
    assert _facts(client, second["id"]) == second_before


# ---- duplicate handling ------------------------------------------------------
def test_uploading_the_identical_file_again_returns_the_existing_resume(client, candidate):
    pdf = rf.standard_pdf()
    first = _upload(client, pdf, "resume.pdf")
    again = _upload(client, pdf, "resume (1).pdf")

    assert again["already_uploaded"] is True
    assert again["resume"]["id"] == first["resume"]["id"]
    assert again["facts_extracted"] == 0
    assert len(client.get("/api/resumes").json()) == 1
    assert len(client.get("/api/candidate/facts").json()) == sum(rf.EXPECTED_COUNTS.values())


def test_reprocess_does_not_duplicate_or_lose_reviewed_records(client, candidate):
    resume = _upload(client, rf.standard_pdf(), "resume.pdf")["resume"]
    facts = _facts(client, resume["id"])
    project = _by_type(facts, "project")[0]
    job = _by_type(facts, "work_experience")[0]
    for fact in (project, job):
        assert client.patch(f"/api/candidate/facts/{fact['id']}", json={"verification_status": "verified"}).status_code == 200

    result = client.post(f"/api/resumes/{resume['id']}/reprocess")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["facts_preserved"] == 2
    assert body["facts_skipped_duplicate"] == 2
    assert body["facts_replaced"] == sum(rf.EXPECTED_COUNTS.values()) - 2
    assert body["facts_extracted"] == sum(rf.EXPECTED_COUNTS.values()) - 2

    after = _facts(client, resume["id"])
    assert _counts(after) == rf.EXPECTED_COUNTS, "no duplicates, nothing lost"
    by_id = {f["id"]: f for f in after}
    assert by_id[project["id"]]["verification_status"] == "verified"
    assert by_id[job["id"]]["verification_status"] == "verified"
    assert by_id[project["id"]]["fact_value"] == project["fact_value"]


def test_reprocess_does_not_resurrect_a_rejected_record(client, candidate):
    resume = _upload(client, rf.standard_pdf(), "resume.pdf")["resume"]
    project = _by_type(_facts(client, resume["id"]), "project")[1]
    assert client.patch(f"/api/candidate/facts/{project['id']}", json={"verification_status": "rejected"}).status_code == 200

    body = client.post(f"/api/resumes/{resume['id']}/reprocess").json()
    assert body["facts_skipped_duplicate"] == 1

    after = _facts(client, resume["id"])
    assert _counts(after) == rf.EXPECTED_COUNTS
    assert {f["id"]: f["verification_status"] for f in after}[project["id"]] == "rejected"


def test_an_updated_resume_skips_unchanged_reviewed_records_and_flags_the_changed_one(client, candidate):
    first = _upload(client, rf.standard_pdf(), "resume-v1.pdf")["resume"]
    first_facts = _facts(client, first["id"])
    ids = [f["id"] for f in first_facts]
    bulk = client.post("/api/candidate/facts/bulk", json={"fact_ids": ids, "verification_status": "verified"})
    assert bulk.status_code == 200, bulk.text
    alpha_v1 = _by_type(first_facts, "project")[0]

    updated = rf.standard_pdf(_updated_sections("Added Redis caching to reduce p95 latency."))
    second = _upload(client, updated, "resume-v2.pdf")
    total = sum(rf.EXPECTED_COUNTS.values())
    assert second["facts_skipped_duplicate"] == total - 1
    assert second["facts_extracted"] == 1

    (new_alpha,) = _facts(client, second["resume"]["id"])
    assert new_alpha["fact_type"] == "project" and new_alpha["fact_value"]["name"] == "Alpha Queue"
    assert new_alpha["verification_status"] == "unverified"
    assert new_alpha["fact_value"]["needs_review"] is True
    assert new_alpha["fact_value"]["possible_duplicate_of"] == alpha_v1["id"]
    assert len(new_alpha["fact_value"]["bullets"]) == 5

    # The reviewed v1 record is unchanged, and the old resume was not touched.
    v1_after = {f["id"]: f for f in _facts(client, first["id"])}
    assert v1_after[alpha_v1["id"]]["verification_status"] == "verified"
    assert v1_after[alpha_v1["id"]]["fact_value"] == alpha_v1["fact_value"]
    assert len(v1_after) == total

    # Flagged records cannot be bulk-verified; the human reviews them one at a time.
    refused = client.post(
        "/api/candidate/facts/bulk",
        json={"fact_ids": [new_alpha["id"]], "verification_status": "verified"},
    )
    assert refused.status_code == 422
    assert "flagged for review" in refused.json()["detail"]
    assert _facts(client, second["resume"]["id"])[0]["verification_status"] == "unverified"

    single = client.patch(f"/api/candidate/facts/{new_alpha['id']}", json={"verification_status": "verified"})
    assert single.status_code == 200
    assert single.json()["verification_status"] == "verified"


# ---- ambiguity is flagged and gated ------------------------------------------
def test_ambiguous_record_is_flagged_and_bulk_verify_is_atomic(client, candidate):
    sections = [
        Section(
            "EXPERIENCE",
            [
                t("Omega Works — Wizard"),
                t("Tulsa, OK | 2017–2018"),
                b("Filed records and handled the front desk."),
                t("Northwind Co — Analyst"),
                t("Remote | 2019–2020"),
                b("Prepared quarterly reports."),
            ],
        )
    ]
    resume = _upload(client, rf.standard_pdf(sections), "ambiguous.pdf")["resume"]
    facts = _facts(client, resume["id"])
    flagged = next(f for f in facts if f["fact_value"]["needs_review"])
    clean = next(f for f in facts if not f["fact_value"]["needs_review"])
    assert flagged["fact_value"]["employer"] is None and flagged["fact_value"]["position"] is None
    assert flagged["fact_value"]["ambiguous_fields"] == ["employer", "position"]
    assert flagged["fact_value"]["location"] == "Tulsa, OK"

    refused = client.post(
        "/api/candidate/facts/bulk",
        json={"fact_ids": [clean["id"], flagged["id"]], "verification_status": "verified"},
    )
    assert refused.status_code == 422
    # All-or-nothing: the clean fact in the same request was not verified either.
    statuses = {f["id"]: f["verification_status"] for f in _facts(client, resume["id"])}
    assert statuses[clean["id"]] == "unverified" and statuses[flagged["id"]] == "unverified"

    # Rejecting flagged facts in bulk is still allowed (it is not a trust decision).
    rejected = client.post(
        "/api/candidate/facts/bulk",
        json={"fact_ids": [flagged["id"]], "verification_status": "rejected"},
    )
    assert rejected.status_code == 200
    # And an unflagged record can be verified as a whole in one action.
    whole = client.patch(f"/api/candidate/facts/{clean['id']}", json={"verification_status": "verified"})
    assert whole.status_code == 200 and whole.json()["fact_value"]["employer"] == "Northwind Co"
