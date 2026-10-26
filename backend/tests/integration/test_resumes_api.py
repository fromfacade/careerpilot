"""Integration tests for resume upload/parsing/fact-review endpoints.

Storage is redirected to a per-test `tmp_path` directory (never the real
`backend/storage/resumes/`) by monkeypatching `get_settings` as imported
into `app.api.resumes` -- this keeps the test suite from littering real
disk storage with throwaway uploads, mirroring how the rest of the suite
never makes real network calls either.
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from app.core.config import get_settings


@pytest.fixture()
def isolated_resume_settings(tmp_path, monkeypatch):
    overridden = get_settings().model_copy(
        update={"resume_storage_dir": str(tmp_path / "resumes"), "resume_max_upload_mb": 10.0}
    )
    monkeypatch.setattr("app.api.resumes.get_settings", lambda: overridden)
    return overridden


def _build_minimal_pdf(lines: list[str]) -> bytes:
    content_ops = ["BT", "/F1 12 Tf", "72 712 Td"]
    for i, line in enumerate(lines):
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if i > 0:
            content_ops.append("0 -14 Td")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    stream_body = "\n".join(content_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream_body)).encode("ascii") + b" >>\nstream\n" + stream_body + b"\nendstream",
    ]

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{i} 0 obj\n".encode("ascii"))
        buffer.write(body)
        buffer.write(b"\nendobj\n")

    xref_offset = buffer.tell()
    n = len(objects) + 1
    buffer.write(f"xref\n0 {n}\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buffer.write(f"{off:010d} 00000 n \n".encode("ascii"))
    buffer.write(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii"))
    return buffer.getvalue()


_SAMPLE_RESUME_TEXT = [
    "Jane Doe",
    "EDUCATION",
    "University of Example - B.S. Computer Science",
    "2021 - 2025",
    "SKILLS",
    "Languages: Python, TypeScript",
]


def _make_candidate(client):
    resp = client.post(
        "/api/candidate",
        json={"full_name": "Jane Doe", "email": "jane.doe@example.com"},
    )
    assert resp.status_code == 201
    return resp.json()


def test_upload_requires_existing_candidate(client, isolated_resume_settings):
    files = {"file": ("resume.pdf", _build_minimal_pdf(["Jane Doe"]), "application/pdf")}
    resp = client.post("/api/resumes", files=files)
    assert resp.status_code == 404


def test_upload_rejects_unsupported_extension(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.txt", b"plain text resume", "text/plain")}
    resp = client.post("/api/resumes", files=files)
    assert resp.status_code == 415


def test_upload_rejects_oversized_file(client, tmp_path, monkeypatch):
    _make_candidate(client)
    tiny_limit = get_settings().model_copy(
        update={"resume_storage_dir": str(tmp_path / "resumes"), "resume_max_upload_mb": 0.0001}
    )
    monkeypatch.setattr("app.api.resumes.get_settings", lambda: tiny_limit)

    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    resp = client.post("/api/resumes", files=files)
    assert resp.status_code == 413


def test_upload_pdf_success_creates_resume_and_facts(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    resp = client.post("/api/resumes", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["resume"]["parse_status"] == "success"
    assert body["resume"]["original_filename"] == "resume.pdf"
    assert body["facts_extracted"] > 0


def test_upload_docx_success(client, isolated_resume_settings):
    _make_candidate(client)
    document = Document()
    for line in _SAMPLE_RESUME_TEXT:
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)

    files = {
        "file": (
            "resume.docx",
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    resp = client.post("/api/resumes", files=files)
    assert resp.status_code == 201
    assert resp.json()["resume"]["parse_status"] == "success"


def test_malformed_pdf_upload_succeeds_but_parse_fails_gracefully(client, isolated_resume_settings):
    """A parse failure must never lose the original upload or crash the
    request -- the resume row is persisted with parse_status=failed."""
    _make_candidate(client)
    files = {"file": ("resume.pdf", b"%PDF-1.4\nthis is not actually a valid pdf body", "application/pdf")}
    resp = client.post("/api/resumes", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["resume"]["parse_status"] == "failed"
    assert body["resume"]["parse_error"]
    assert body["facts_extracted"] == 0

    # The resume row genuinely persisted, not just reflected in the response.
    get_resp = client.get(f"/api/resumes/{body['resume']['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["parse_status"] == "failed"


def test_list_resumes_and_facts_for_resume(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    upload = client.post("/api/resumes", files=files).json()
    resume_id = upload["resume"]["id"]

    list_resp = client.get("/api/resumes")
    assert list_resp.status_code == 200
    assert any(r["id"] == resume_id for r in list_resp.json())

    facts_resp = client.get(f"/api/resumes/{resume_id}/facts")
    assert facts_resp.status_code == 200
    facts = facts_resp.json()
    assert len(facts) == upload["facts_extracted"]
    assert all(f["verification_status"] == "unverified" for f in facts)
    assert all(f["resume_id"] == resume_id for f in facts)


def test_candidate_facts_filtering_by_type(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    client.post("/api/resumes", files=files)

    resp = client.get("/api/candidate/facts", params={"fact_type": "skill"})
    assert resp.status_code == 200
    facts = resp.json()
    assert len(facts) > 0
    assert all(f["fact_type"] == "skill" for f in facts)


def test_update_fact_marks_verified(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    client.post("/api/resumes", files=files)
    fact_id = client.get("/api/candidate/facts").json()[0]["id"]

    resp = client.patch(f"/api/candidate/facts/{fact_id}", json={"verification_status": "verified"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification_status"] == "verified"
    assert body["verified_at"] is not None


def test_update_fact_editing_content_without_status_auto_marks_edited(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    client.post("/api/resumes", files=files)
    fact_id = client.get("/api/candidate/facts").json()[0]["id"]

    resp = client.patch(f"/api/candidate/facts/{fact_id}", json={"fact_key": "Corrected label"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fact_key"] == "Corrected label"
    assert body["verification_status"] == "edited"


def test_update_fact_rejects_reverting_to_unverified(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    client.post("/api/resumes", files=files)
    fact_id = client.get("/api/candidate/facts").json()[0]["id"]

    resp = client.patch(f"/api/candidate/facts/{fact_id}", json={"verification_status": "unverified"})
    assert resp.status_code == 422


def test_rejected_facts_are_kept_not_deleted(client, isolated_resume_settings):
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    client.post("/api/resumes", files=files)
    fact_id = client.get("/api/candidate/facts").json()[0]["id"]

    resp = client.patch(f"/api/candidate/facts/{fact_id}", json={"verification_status": "rejected"})
    assert resp.status_code == 200

    all_facts = client.get("/api/candidate/facts").json()
    assert any(f["id"] == fact_id and f["verification_status"] == "rejected" for f in all_facts)


def test_resume_has_no_update_endpoint(client, isolated_resume_settings):
    """Immutability is structural: there is no PATCH/PUT for a resume."""
    _make_candidate(client)
    files = {"file": ("resume.pdf", _build_minimal_pdf(_SAMPLE_RESUME_TEXT), "application/pdf")}
    resume_id = client.post("/api/resumes", files=files).json()["resume"]["id"]

    assert client.patch(f"/api/resumes/{resume_id}", json={"original_filename": "hacked.pdf"}).status_code == 405
    assert client.put(f"/api/resumes/{resume_id}", json={"original_filename": "hacked.pdf"}).status_code == 405
