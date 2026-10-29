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
