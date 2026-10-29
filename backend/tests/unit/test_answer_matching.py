"""Context-aware reuse of approved Greenhouse answers. Fictional data only."""

from app.autofill.mapping import ProfileView, plan_autofill
from app.autofill.materials import AnswerView, Materials

URL = "https://boards.greenhouse.io/northwind/jobs/15"
PROFILE = ProfileView(candidate_id=7, full_name="Ada Lovelace", email="ada@example.com")


def _form(label: str, field_id: str = "q") -> str:
    return f"""
    <form id="application">
      <label for="{field_id}">{label}</label>
      <textarea id="{field_id}" name="{field_id}"></textarea>
    </form>
    """


def _answer(answer_id: int, question: str, text: str, **overrides) -> AnswerView:
    data = dict(
        id=answer_id,
        question=question,
        answer_text=text,
        approval_status="approved",
        origin="manual",
        category="experience",
        is_sensitive=False,
        is_reusable=True,
        is_preferred=False,
        source="library",
        role="",
    )
    data.update(overrides)
    return AnswerView(**data)


def _plan(label: str, answers: list[AnswerView], *, employer: str = "Northwind", role: str = "Backend Intern", job: list[AnswerView] | None = None):
    materials = Materials(employer=employer, role=role, library_answers=answers, job_answers=job or [])
    return plan_autofill(URL, _form(label), [], PROFILE, materials)


def test_equivalent_python_wording_is_reused():
    answer = _answer(1, "Tell us about your Python experience", "I write Python services.")
    plan = _plan("Describe your experience with Python", [answer])
    matched = plan.answers.matched[0]
    assert matched.match_kind == "equivalent_match"
    assert matched.eligible_for_fill is True
    assert matched.review_required is False
    assert matched.proposed_text == "I write Python services."
    assert "Python experience" in matched.explanation
    assert "equivalent" in matched.explanation


def test_a_stripe_answer_is_not_filled_into_a_dropbox_application():
    answer = _answer(2, "Why do you want to work at Stripe?", "I want to join Stripe.")
    plan = _plan("Why do you want to work at Dropbox?", [answer], employer="Dropbox", role="Backend Intern")
    assert plan.answers.matched == []
    reviewed = plan.answers.ambiguous[0]
    assert reviewed.match_kind == "uncertain_match"
    assert reviewed.eligible_for_fill is False
    assert "different employer" in reviewed.explanation


def test_python_experience_is_not_reused_for_java():
    answer = _answer(3, "Describe your experience with Python", "I write Python services.")
    plan = _plan("Describe your experience with Java", [answer])
    assert plan.answers.matched == []
    assert plan.answers.ambiguous == []
    missing = plan.answers.missing[0]
    assert missing.match_kind == "no_match"
    assert missing.proposed_text is None
    assert "Python" not in (missing.proposed_text or "")


def test_a_backend_answer_is_not_reused_for_a_frontend_role():
    answer = _answer(
        4,
        "Why are you interested in this backend internship?",
        "I build backend services and APIs.",
        role="Backend Intern",
    )
    plan = _plan("Why are you interested in this role?", [answer], employer="Northwind", role="Frontend Intern")
    assert plan.answers.matched == []
    assert all(item.proposed_text is None for item in plan.answers.missing + plan.answers.ambiguous)


def test_a_library_start_date_requires_review():
    answer = _answer(5, "When can you start?", "June 2026", category="logistics")
    plan = _plan("When can you start?", [answer])
    assert plan.answers.matched == []
    reviewed = plan.answers.ambiguous[0]
    assert reviewed.match_kind == "uncertain_match"
    assert reviewed.proposed_text == "June 2026"
    assert reviewed.eligible_for_fill is False
    assert "start date" in reviewed.explanation


def test_conflicting_approved_answers_are_not_chosen():
    first = _answer(6, "Describe your relevant experience", "One experience.")
    second = _answer(7, "Tell us about your professional experience", "Another experience.")
    plan = _plan("Describe your professional experience", [first, second])
    assert plan.answers.matched == []
    reviewed = plan.answers.ambiguous[0]
    assert reviewed.proposed_text is None
    assert reviewed.match_kind == "uncertain_match"
    assert "more than one" in reviewed.explanation.casefold()


def test_job_specific_exact_answer_wins_over_the_library():
    library = _answer(8, "Why are you interested in this role?", "Library wording.")
    job = _answer(9, "Why are you interested in this role?", "This Northwind answer.", source="job_specific")
    plan = _plan("Why are you interested in this role?", [library], job=[job])
    matched = plan.answers.matched[0]
    assert matched.proposed_text == "This Northwind answer."
    assert matched.source == "job_specific"
    assert matched.match_kind == "exact_match"
    assert "this application already has" in matched.explanation


def test_unapproved_drafts_are_not_promoted():
    draft = _answer(10, "Describe your experience with Python", "Invented Python work.", approval_status="draft", origin="ai_draft")
    plan = _plan("Describe your experience with Python", [draft])
    assert plan.answers.matched == []
    assert draft.answer_text not in str(plan.answers)


def test_sensitive_questions_stay_manual():
    html = """
    <form id="application">
      <label for="auth">Are you authorized to work in the United States?</label>
      <select id="auth" name="auth"><option>Yes</option><option>No</option></select>
      <label for="agree">I agree to the terms and conditions</label>
      <input id="agree" name="agree" type="checkbox">
    </form>
    """
    answer = _answer(11, "Are you authorized to work in the United States?", "Yes", category="work_authorization", is_sensitive=True)
    plan = plan_autofill(URL, html, [], PROFILE, Materials(employer="Northwind", role="Backend Intern", library_answers=[answer]))
    assert plan.answers.matched == []
    assert all(item.proposed_text is None for item in plan.answers.sensitive)
    assert "Yes" not in str(plan.answers)


def test_shared_keywords_with_a_different_meaning_do_not_match():
    answer = _answer(12, "Why are you interested in this role?", "I like this kind of work.")
    plan = _plan("What is your greatest strength?", [answer])
    assert plan.answers.matched == []
    assert plan.answers.ambiguous == []
    assert plan.answers.missing[0].match_kind == "no_match"
    assert plan.answers.missing[0].proposed_text is None
