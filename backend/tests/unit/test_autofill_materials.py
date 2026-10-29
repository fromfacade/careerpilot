from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.autofill.executor import BrowserFillUnavailable, form_executor
from app.autofill.mapping import FactView, ProfileView, plan_autofill
from app.autofill.materials import AnswerView, Materials, ResumeFileView, TailoredFileView
from app.core.local_guard import LocalRequestGuard, local_request_allowed
from app.schemas.autofill import to_plan_result

URL = "https://boards.greenhouse.io/acme/jobs/12345"
PROFILE = ProfileView(candidate_id=7, full_name="Ada Lovelace", email="ada@example.com")
SECRET = "I enjoy building small tools."
DRAFT = "Invented qualification: shipped a satellite alone."
AUTH = "I am a citizen."
SPONSOR = "I will not need sponsorship."

FORM = """
<form id="application">
  <label for="first">First Name *</label>
  <input id="first" name="job_application[first_name]" required>
  <label for="resume">Resume/CV *</label>
  <input id="resume" name="job_application[resume]" type="file" accept=".pdf" required>
  <label for="why">Why are you interested in this role?</label>
  <textarea id="why" name="why"></textarea>
  <label for="project">Describe a technical project you are proud of. *</label>
  <textarea id="project" name="project" required></textarea>
  <label for="auth">Are you authorized to work in the United States?</label>
  <select id="auth" name="auth" required><option>Yes</option><option>No</option></select>
  <label for="sponsor">Will you now or in the future require visa sponsorship?</label>
  <select id="sponsor" name="sponsor"><option>Yes</option><option>No</option></select>
</form>
"""


def _resume(path, **overrides):
    data = dict(
        resume_id=4,
        display_name="Backend SWE Resume",
        file_format="pdf",
        approved=True,
        archived=False,
        storage_path=str(path),
    )
    data.update(overrides)
    return ResumeFileView(**data)


def _answer(answer_id, question, text, **overrides):
    data = dict(
        id=answer_id,
        question=question,
        answer_text=text,
        approval_status="approved",
        origin="manual",
        category="interest",
        is_sensitive=False,
        is_reusable=True,
        is_preferred=False,
        source="library",
    )
    data.update(overrides)
    return AnswerView(**data)


def _materials(path, **overrides):
    data = dict(
        preparation_id=9,
        resume=_resume(path),
        tailored=TailoredFileView(status="draft"),
        job_answers=[],
        library_answers=[],
        writing_style_profile_id=3,
        link_problem=None,
    )
    data.update(overrides)
    return Materials(**data)


def _plan(path, html=FORM, **materials):
    return plan_autofill(URL, html, [], PROFILE, _materials(path, **materials))


def test_approved_original_resume_is_selected_and_the_file_is_not_rewritten(tmp_path):
    resume = tmp_path / "nested" / "secret-resume.pdf"
    resume.parent.mkdir()
    resume.write_bytes(b"%PDF-1.4 fictional")
    before = resume.read_bytes()
    first = _plan(resume)
    second = _plan(resume)
    assert first.resume.kind == "original"
    assert second.resume.resume_id == first.resume.resume_id == 4
    assert first.resume.eligible_for_attach is True
    assert first.resume.file_format == "pdf"
    assert first.resume.display_name == "Backend SWE Resume"
    dumped = str(to_plan_result(first).model_dump())
    assert str(resume) not in dumped
    assert "secret-resume" not in dumped
    assert resume.read_bytes() == before


def test_missing_unapproved_and_unreadable_resumes_need_review(tmp_path):
    missing = _plan(tmp_path / "gone.pdf")
    assert missing.resume.eligible_for_attach is False
    assert missing.resume.readable is False
    unapproved = _plan(tmp_path / "x.pdf", resume=_resume(tmp_path / "x.pdf", approved=False))
    (tmp_path / "x.pdf").write_bytes(b"%PDF")
    unapproved = _plan(tmp_path / "x.pdf", resume=_resume(tmp_path / "x.pdf", approved=False))
    assert unapproved.resume.eligible_for_attach is False
    assert unapproved.resume.review_required is True
    assert "not substituted" in unapproved.resume.reason
    none = plan_autofill(URL, FORM, [], PROFILE, Materials())
    assert none.resume.status == "unavailable"


def test_tailored_resume_is_used_only_after_explicit_approval(tmp_path):
    original = tmp_path / "original.pdf"
    tailored = tmp_path / "tailored.pdf"
    original.write_bytes(b"%PDF original")
    tailored.write_bytes(b"%PDF tailored")
    draft = _plan(original, tailored=TailoredFileView(status="draft", pdf_path=str(tailored)))
    assert draft.resume.kind == "original"
    assert "tailored.pdf" not in str(to_plan_result(draft).model_dump())
    approved = _plan(original, tailored=TailoredFileView(status="approved", pdf_path=str(tailored)))
    assert approved.resume.kind == "tailored"
    assert approved.resume.display_name == "Tailored resume (PDF)"
    assert approved.resume.eligible_for_attach is True
    assert str(tailored) not in str(to_plan_result(approved).model_dump())
    missing = _plan(original, tailored=TailoredFileView(status="approved", pdf_path=str(tmp_path / "missing.pdf")))
    assert missing.resume.kind == "tailored"
    assert missing.resume.eligible_for_attach is False
    assert "not substituted" in missing.resume.reason
    assert original.read_bytes() == b"%PDF original"


def test_file_format_must_match_the_form(tmp_path):
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"PK fictional")
    refused = _plan(docx, resume=_resume(docx, file_format="docx"))
    assert refused.resume.compatible is False
    assert refused.resume.eligible_for_attach is False
    open_form = FORM.replace('accept=".pdf"', "")
    allowed = _plan(docx, html=open_form, resume=_resume(docx, file_format="docx"))
    assert allowed.resume.compatible is True
    assert allowed.resume.eligible_for_attach is True


def test_job_specific_exact_answer_beats_the_library_and_is_not_rewritten(tmp_path):
    library = _answer(1, "Why are you interested in this role?", "Library wording.")
    job = _answer(2, "  why are you interested in this role? ", SECRET, source="job_specific", origin="manual")
    plan = _plan(tmp_path / "resume.pdf", job_answers=[job], library_answers=[library])
    (tmp_path / "resume.pdf").write_bytes(b"%PDF")
    plan = _plan(tmp_path / "resume.pdf", job_answers=[job], library_answers=[library])
    matched = plan.answers.matched[0]
    assert matched.proposed_text == SECRET
    assert matched.source == "job_specific"
    assert matched.source_id == 2
    assert matched.approval_status == "approved"
    assert matched.eligible_for_fill is True
    assert plan.answers.answers_rewritten is False
    assert plan.answers.writing_style_profile_id == 3


def test_equivalent_interest_wording_is_reused_and_conflicts_are_not_chosen(tmp_path):
    near = _answer(3, "Why are you interested in this position?", SECRET)
    plan = _plan(tmp_path / "a.pdf", library_answers=[near])
    matched = plan.answers.matched[0]
    assert matched.match_kind == "equivalent_match"
    assert matched.eligible_for_fill is True
    assert matched.proposed_text == SECRET
    assert "equivalent" in matched.explanation
    first = _answer(4, "Why are you interested in this role?", "One.")
    second = _answer(5, "Why are you interested in this role?", "Two.")
    ambiguous = _plan(tmp_path / "a.pdf", library_answers=[first, second])
    assert ambiguous.answers.matched == []
    assert ambiguous.answers.ambiguous[0].proposed_text is None
    assert ambiguous.answers.ambiguous[0].match_kind == "uncertain_match"
    assert "more than one" in ambiguous.answers.ambiguous[0].explanation.casefold()


def test_unapproved_drafts_and_sensitive_answers_are_not_inserted(tmp_path):
    draft = _answer(6, "Describe a technical project you are proud of?", DRAFT, approval_status="draft", origin="ai_draft")
    auth = _answer(7, "Are you authorized to work in the United States?", AUTH, category="work_authorization", is_sensitive=True)
    sponsor = _answer(
        8, "Will you now or in the future require visa sponsorship?", SPONSOR, category="sponsorship", is_sensitive=True
    )
    plan = _plan(tmp_path / "a.pdf", library_answers=[draft, auth, sponsor])
    dumped = str(to_plan_result(plan).model_dump())
    assert DRAFT not in dumped
    assert AUTH not in dumped
    assert SPONSOR not in dumped
    assert plan.answers.sensitive
    assert all(item.proposed_text is None for item in plan.answers.sensitive)
    project = next(item for item in plan.answers.missing if item.field_id == "project")
    assert project.proposed_text is None
    assert project.required is True


def test_existing_answer_text_is_preserved(tmp_path):
    html = FORM.replace(
        '<textarea id="why" name="why"></textarea>',
        "<textarea id=\"why\" name=\"why\">Already written.</textarea>",
    )
    answer = _answer(9, "Why are you interested in this role?", SECRET, source="job_specific")
    plan = _plan(tmp_path / "a.pdf", html=html, job_answers=[answer])
    saved = plan.answers.preserved[0]
    assert saved.existing_value == "Already written."
    assert saved.proposed_text is None
    assert saved.proposed_replacement == SECRET
    assert saved.eligible_for_fill is False
    assert all(item.field_id != "why" for item in plan.answers.matched)


def test_rejected_url_and_foreign_origin_do_not_reveal_candidate_data(tmp_path):
    answer = _answer(10, "Why are you interested in this role?", SECRET)
    plan = plan_autofill("https://jobs.lever.co/acme/role", FORM, [], PROFILE, _materials(tmp_path / "a.pdf", library_answers=[answer]))
    assert SECRET not in str(to_plan_result(plan).model_dump())
    assert plan.resume.eligible_for_attach is False
    assert local_request_allowed("evil.test", None, ["http://localhost:5173"]) is False
    assert local_request_allowed("127.0.0.1:8000", "https://evil.test", ["http://localhost:5173"]) is False
    assert local_request_allowed("localhost:5173", "http://localhost:5173", ["http://localhost:5173"]) is True

    app = FastAPI()
    app.add_middleware(LocalRequestGuard)

    @app.get("/secret")
    def secret():
        return {"email": "ada@example.com", "answer": SECRET}

    client = TestClient(app)
    blocked = client.get("/secret", headers={"Origin": "https://evil.test"})
    assert blocked.status_code == 403
    assert SECRET not in blocked.text
    assert "ada@example.com" not in blocked.text
    assert client.get("/secret").status_code == 200


def test_browser_executor_refuses_to_attach_or_fill(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF stay")
    executor = form_executor()
    try:
        executor.attach_file("resume", "Backend SWE Resume", resume.read_bytes())
        raised = False
    except BrowserFillUnavailable:
        raised = True
    assert raised is True
    try:
        executor.fill_text("email", "ada@example.com")
        raised = False
    except BrowserFillUnavailable:
        raised = True
    assert raised is True
    assert resume.read_bytes() == b"%PDF stay"
