"""HTTP tests for the canonical knowledge-base API and resume-delete isolation."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from tests.resume_fixtures import EXPECTED_COUNTS, standard_pdf


@pytest.fixture()
def isolated_resume_settings(tmp_path, monkeypatch):
    overridden = get_settings().model_copy(
        update={"resume_storage_dir": str(tmp_path / "resumes"), "resume_max_upload_mb": 10.0}
    )
    monkeypatch.setattr("app.api.resumes.get_settings", lambda: overridden)
    return overridden


@pytest.fixture()
def candidate(client, isolated_resume_settings):
    resp = client.post("/api/candidate", json={"full_name": "Jane Doe", "email": "jane.kb@example.com"})
    assert resp.status_code == 201
    return resp.json()


def _upload_and_verify(client):
    upload = client.post(
        "/api/resumes",
        files={"file": ("resume.pdf", standard_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    resume = upload.json()["resume"]
    facts = client.get(f"/api/resumes/{resume['id']}/facts").json()
    ids = [f["id"] for f in facts]
    bulk = client.post("/api/candidate/facts/bulk", json={"fact_ids": ids, "verification_status": "verified"})
    assert bulk.status_code == 200, bulk.text
    return resume, facts


def test_import_endpoint_promotes_verified_facts(client, candidate):
    resume, facts = _upload_and_verify(client)
    imported = client.post("/api/candidate/canonical-facts/import", json={})
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created"] == sum(EXPECTED_COUNTS.values())
    assert body["conflicts"] == 0
    listed = client.get("/api/candidate/canonical-facts").json()
    assert len(listed) == body["created"]
    assert {row["status"] for row in listed} == {"active"}
    assert all(row["sources"] for row in listed)
    assert all(row["sources"][0]["resume_id"] == resume["id"] for row in listed)
    assert {row["sources"][0]["candidate_fact_id"] for row in listed} == {f["id"] for f in facts}


def test_manual_create_edit_verify_and_filters(client, candidate):
    created = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "skill", "fact_key": "Languages", "fact_value": {"items": ["English"]}},
    )
    assert created.status_code == 201, created.text
    assert created.json()["verification_status"] == "unverified"
    fact_id = created.json()["id"]

    edited = client.patch(
        f"/api/candidate/canonical-facts/{fact_id}",
        json={"fact_value": {"items": ["English", "Spanish"]}},
    )
    assert edited.status_code == 200
    assert edited.json()["verification_status"] == "edited"
    assert edited.json()["fact_value"]["items"] == ["English", "Spanish"]

    verified = client.patch(
        f"/api/candidate/canonical-facts/{fact_id}",
        json={"verification_status": "verified"},
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"

    filtered = client.get(
        "/api/candidate/canonical-facts",
        params={"fact_type": "skill", "status": "active", "verification_status": "verified"},
    )
    assert [row["id"] for row in filtered.json()] == [fact_id]

    duplicate = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "skill", "fact_key": "languages", "fact_value": {"items": ["French"]}},
    )
    assert duplicate.status_code == 409


def test_deleting_a_resume_leaves_canonical_facts_and_clears_provenance_pointers(client, candidate):
    resume, facts = _upload_and_verify(client)
    imported = client.post("/api/candidate/canonical-facts/import", json={})
    assert imported.status_code == 200
    before = client.get("/api/candidate/canonical-facts").json()
    assert before

    deleted = client.request("DELETE", f"/api/resumes/{resume['id']}", json={"delete_verified_facts": False})
    assert deleted.status_code == 200, deleted.text

    after = client.get("/api/candidate/canonical-facts").json()
    assert {row["id"] for row in after} == {row["id"] for row in before}
    assert {row["fact_key"] for row in after} == {row["fact_key"] for row in before}
    for row in after:
        assert row["fact_value"] == next(b["fact_value"] for b in before if b["id"] == row["id"])
        assert row["sources"]
        assert row["sources"][0]["resume_id"] is None
        # Extracted records were detached, not deleted.
        assert row["sources"][0]["candidate_fact_id"] is not None

    leftover_extracted = client.get("/api/candidate/facts").json()
    assert {f["id"] for f in leftover_extracted} == {f["id"] for f in facts}
    assert all(f["resume_id"] is None for f in leftover_extracted)


def test_explicitly_deleting_verified_extracted_facts_still_keeps_canonical_rows(client, candidate):
    resume, _facts = _upload_and_verify(client)
    imported = client.post("/api/candidate/canonical-facts/import", json={})
    canonical_ids = {row["id"] for row in imported.json()["facts"]}

    deleted = client.request("DELETE", f"/api/resumes/{resume['id']}", json={"delete_verified_facts": True})
    assert deleted.status_code == 200
    after = client.get("/api/candidate/canonical-facts").json()
    assert {row["id"] for row in after} == canonical_ids
    for row in after:
        assert row["sources"][0]["resume_id"] is None
        assert row["sources"][0]["candidate_fact_id"] is None
    assert client.get("/api/candidate/facts").json() == []


def test_conflict_resolve_and_archive_via_api(client, candidate):
    first = client.post(
        "/api/candidate/canonical-facts",
        json={"fact_type": "project", "fact_key": "Alpha", "fact_value": {"name": "Alpha", "bullets": ["One."]}},
    )
    assert first.status_code == 201
    client.patch(f"/api/candidate/canonical-facts/{first.json()['id']}", json={"verification_status": "verified"})

    # A second resume-derived fact with the same name arrives via the extracted-fact table.
    upload = client.post(
        "/api/resumes",
        files={"file": ("other.pdf", standard_pdf(), "application/pdf")},
    )
    resume_id = upload.json()["resume"]["id"]
    extracted = client.get(f"/api/resumes/{resume_id}/facts").json()
    project = next(f for f in extracted if f["fact_type"] == "project" and f["fact_key"] == "Alpha Queue")
    # Rename it to collide with the manual Alpha, then verify and import.
    client.patch(
        f"/api/candidate/facts/{project['id']}",
        json={"fact_key": "Alpha", "fact_value": {"name": "Alpha", "bullets": ["One.", "Two."]}, "verification_status": "verified"},
    )
    imported = client.post("/api/candidate/canonical-facts/import", json={"fact_ids": [project["id"]]})
    assert imported.status_code == 200
    assert imported.json()["conflicts"] == 1
    conflict = imported.json()["facts"][0]
    assert conflict["status"] == "conflict"

    resolved = client.post(
        f"/api/candidate/canonical-facts/{conflict['id']}/resolve",
        json={"keep": "existing"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["fact_value"]["bullets"] == ["One."]
    assert resolved.json()["status"] == "active"

    archived = client.post(f"/api/candidate/canonical-facts/{conflict['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
