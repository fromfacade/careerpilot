"""Common Greenhouse controls keep their question when the markup changes."""

from app.autofill.actions import decide_fill, revealed_actions, reviewed_fields
from app.autofill.mapping import FactView, ProfileView, plan_autofill
from app.autofill.materials import AnswerView, Materials

URL = "https://boards.greenhouse.io/northwind/jobs/15"
PROFILE = ProfileView(
    candidate_id=7,
    full_name="Ada Lovelace",
    email="ada@example.com",
    phone="555-0100",
    major="Computer Science",
)
EDUCATION = FactView(
    id=3,
    fact_type="education",
    fact_key="Example State University",
    fact_value={"institution": "Example State University", "degree": "Bachelor's", "major": "Computer Science"},
    identity_key="education|example",
    status="active",
    verification_status="verified",
)


def _answer(question: str, text: str, answer_id: int = 1) -> AnswerView:
    return AnswerView(
        id=answer_id,
        question=question,
        answer_text=text,
        approval_status="approved",
        origin="manual",
        category="experience",
        is_sensitive=False,
        is_reusable=True,
        source="library",
    )


def _form(body: str) -> str:
    return f'<form id="application">{body}</form>'


RELOCATE = _form(
    """
    <fieldset>
      <legend>Are you willing to relocate?</legend>
      <label><input type="radio" name="relocate" value="yes"> Yes</label>
      <label><input type="radio" name="relocate" value="no"> No</label>
    </fieldset>
    """
)

QUESTION = "Which of these do you know: Python, SQL, or Java?"
LANGUAGES = _form(
    f"""
    <label for="languages">{QUESTION}</label>
    <select id="languages" name="languages" multiple>
      <option>Python</option>
      <option>SQL</option>
      <option>Java</option>
    </select>
    """
)


def test_a_relocating_radio_uses_an_exact_approved_answer():
    materials = Materials(library_answers=[_answer("Are you willing to relocate?", "Yes")])
    plan = plan_autofill(URL, RELOCATE, [], PROFILE, materials)
    chosen = plan.answers.matched[0]
    assert chosen.input_type == "radio"
    assert chosen.proposed_text == "Yes"
    assert chosen.eligible_for_fill is True
    reviewed = reviewed_fields(plan)
    assert reviewed["relocate"].input_type == "radio"


def test_a_radio_answer_that_is_not_listed_stays_for_review():
    materials = Materials(library_answers=[_answer("Are you willing to relocate?", "Maybe")])
    plan = plan_autofill(URL, RELOCATE, [], PROFILE, materials)
    assert plan.answers.matched == []
    assert "exactly matches" in (plan.answers.ambiguous[0].explanation or "")


def test_a_multi_select_uses_each_exact_approved_choice():
    materials = Materials(library_answers=[_answer(QUESTION, "Python, SQL")])
    plan = plan_autofill(URL, LANGUAGES, [], PROFILE, materials)
    chosen = plan.answers.matched[0]
    assert chosen.input_type == "multi_select"
    assert chosen.proposed_text == "Python\nSQL"
    assert chosen.eligible_for_fill is True


def test_a_moved_control_keeps_the_same_question():
    original = _form('<label for="old_school">School</label><select id="old_school" name="old_school"><option>Example State University</option></select>')
    moved = _form('<label for="new_school">School</label><select id="new_school" name="new_school"><option>Example State University</option></select>')
    before = plan_autofill(URL, original, [EDUCATION], PROFILE, Materials())
    after = plan_autofill(URL, moved, [EDUCATION], PROFILE, Materials())
    decision = decide_fill(
        reviewed_fields(before),
        after,
        included={"old_school"},
        overwrite=set(),
        attach_resume=False,
    )
    assert decision.stale == []
    assert decision.actions[0].input_type == "select"
    assert decision.actions[0].name == "new_school"
    assert decision.actions[0].element_id == "new_school"
    assert decision.actions[0].value == "Example State University"


def test_two_identical_questions_are_left_for_review_when_their_ids_change():
    original = _form(
        """
        <label for="one">Why this role?</label><textarea id="one" name="one"></textarea>
        <label for="two">Why this role?</label><textarea id="two" name="two"></textarea>
        """
    )
    moved = _form(
        """
        <label for="three">Why this role?</label><textarea id="three" name="three"></textarea>
        <label for="four">Why this role?</label><textarea id="four" name="four"></textarea>
        """
    )
    answer = _answer("Why this role?", "I want to build the payments ledger.")
    materials = Materials(library_answers=[answer])
    before = plan_autofill(URL, original, [], PROFILE, materials)
    after = plan_autofill(URL, moved, [], PROFILE, materials)
    decision = decide_fill(
        reviewed_fields(before),
        after,
        included=set(reviewed_fields(before)),
        overwrite=set(),
        attach_resume=False,
    )
    assert decision.actions == []
    assert set(decision.stale_details) == {"one", "two"}
    assert "More than one field" in decision.stale_details["one"]


def test_a_hidden_follow_up_is_filled_from_verified_facts_once_it_appears():
    hidden = _form(
        """
        <label for="email">Email</label><input id="email" name="email" type="email">
        <div hidden><label for="major">Major</label><input id="major" name="major"></div>
        """
    )
    shown = _form(
        """
        <label for="email">Email</label><input id="email" name="email" type="email">
        <label for="major">Major</label><input id="major" name="major">
        """
    )
    first = plan_autofill(URL, hidden, [EDUCATION], PROFILE, Materials())
    second = plan_autofill(URL, shown, [EDUCATION], PROFILE, Materials())
    assert all(item.field_id != "major" for item in first.ready)
    follow = revealed_actions(reviewed_fields(first), second, done={"email"})
    assert [action.field_id for action in follow.actions] == ["major"]
    assert follow.actions[0].value == "Computer Science"


COMMON = _form(
    """
    <label for="year">Graduation year</label>
    <select id="year" name="year"><option>2026</option><option>2027</option></select>
    <label for="grad_text">Graduation date</label>
    <input id="grad_text" name="grad_text" type="text">
    <label for="employment">Employment type</label>
    <input id="employment" name="employment" role="combobox" aria-label="Employment type">
    <label for="office">Preferred office</label>
    <select id="office" name="office"><option>Austin, TX</option><option>Remote</option></select>
    <label for="track">Engineering specialization</label>
    <select id="track" name="track"><option>Computer Science</option><option>Design</option></select>
    <label for="spec_note">Engineering specialization</label>
    <textarea id="spec_note" name="spec_note"></textarea>
    <label for="categories">Relevant experience categories</label>
    <select id="categories" name="categories"><option>Internships</option><option>Research</option></select>
    <label for="start">Availability</label>
    <select id="start" name="start"><option>Summer 2027</option><option>Immediately</option></select>
    <div hidden>
      <label for="template_year">Graduation year</label>
      <select id="template_year" name="template_year"><option>2027</option></select>
    </div>
    """
)


def test_common_dropdowns_use_one_exact_verified_or_approved_choice():
    education = FactView(
        id=4,
        fact_type="education",
        fact_key="Example State University",
        fact_value={"institution": "Example State University", "major": "Computer Science", "end_date": "2027-05"},
        identity_key="education|example",
        status="active",
        verification_status="verified",
    )
    profile = ProfileView(candidate_id=7, full_name="Ada Lovelace", email="ada@example.com", location="Austin, TX", major="Computer Science")
    start = AnswerView(
        id=11,
        question="Availability",
        answer_text="Summer 2027",
        approval_status="approved",
        origin="manual",
        category="availability",
        source="job_specific",
    )
    materials = Materials(
        library_answers=[
            _answer("Employment type", "Internship", 12),
            _answer("Relevant experience categories", "Internships", 13),
        ],
        job_answers=[start],
    )
    plan = plan_autofill(URL, COMMON, [education], profile, materials)
    year = next(item for item in plan.answers.matched if item.field_id == "year")
    assert year.proposed_text == "2027"
    assert year.explanation == "Verified graduation year."
    office = next(item for item in plan.answers.matched if item.field_id == "office")
    assert office.proposed_text == "Austin, TX"
    employment = next(item for item in plan.answers.matched if item.field_id == "employment")
    assert employment.input_type == "combobox"
    assert employment.proposed_text == "Internship"
    categories = next(item for item in plan.answers.matched if item.field_id == "categories")
    assert categories.proposed_text == "Internships"
    availability = next(item for item in plan.answers.matched if item.field_id == "start")
    assert availability.proposed_text == "Summer 2027"
    assert any(item.field_id == "track" and item.proposed_value == "Computer Science" for item in plan.ready)
    assert all(item.field_id != "grad_text" or not item.eligible_for_fill for item in plan.answers.matched)
    assert all(item.field_id != "template_year" for item in plan.answers.matched + plan.answers.missing)
    note = next(item for item in plan.answers.missing if item.field_id == "spec_note")
    assert note.proposed_text is None


def test_a_similar_dropdown_choice_is_not_selected():
    materials = Materials(library_answers=[_answer("Employment type", "Intern")])
    form = _form(
        """
        <label for="employment">Employment type</label>
        <select id="employment" name="employment"><option>Internship</option><option>Full-time</option></select>
        """
    )
    plan = plan_autofill(URL, form, [], PROFILE, materials)
    assert plan.answers.matched == []
    assert "exactly matches" in (plan.answers.ambiguous[0].explanation or "")


def test_a_revealed_custom_question_stays_for_review():
    hidden = _form('<div hidden><label for="employment">Employment type</label><select id="employment" name="employment"><option>Internship</option></select></div>')
    shown = _form('<label for="employment">Employment type</label><select id="employment" name="employment"><option>Internship</option></select>')
    materials = Materials(library_answers=[_answer("Employment type", "Internship")])
    first = plan_autofill(URL, hidden, [], PROFILE, materials)
    second = plan_autofill(URL, shown, [], PROFILE, materials)
    follow = revealed_actions(reviewed_fields(first), second, done=set())
    assert follow.actions == []
    assert second.answers.matched[0].proposed_text == "Internship"
