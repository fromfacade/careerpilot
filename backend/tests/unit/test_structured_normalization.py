"""Verified schools and degrees match one employer option without changing the fact."""

from app.autofill.mapping import FactView, ProfileView, plan_autofill
from app.autofill.materials import Materials
from app.autofill.normalize import match_choice

URL = "https://boards.greenhouse.io/northwind/jobs/15"


def _education(institution: str, degree: str, major: str = "Computer Science") -> FactView:
    return FactView(
        id=3,
        fact_type="education",
        fact_key=institution,
        fact_value={"institution": institution, "degree": degree, "major": major},
        identity_key="education|example",
        status="active",
        verification_status="verified",
    )


def _form(body: str) -> str:
    return f'<form id="application">{body}</form>'


def test_university_punctuation_and_abbreviations_match_one_campus():
    verified = "University of California, Santa Cruz"
    option = "University of California - Santa Cruz"
    found = match_choice("school", verified, [option])
    assert found.option == option
    assert found.explanation == (
        "Selected University of California - Santa Cruz because it matches your verified school: "
        "University of California, Santa Cruz."
    )
    assert match_choice("school", "UC Santa Cruz", [option]).option == option
    assert match_choice("school", "UCSC", [option]).option == option
    assert match_choice("school", verified, ["University of California, Santa Cruz"]).explanation == ""


def test_different_uc_campuses_do_not_match():
    options = [
        "University of California - Berkeley",
        "University of California - Los Angeles",
        "University of California - San Diego",
    ]
    found = match_choice("school", "UC Santa Cruz", options)
    assert found.option is None
    assert "exactly matches" in found.explanation
    assert match_choice("school", "University of California", ["University of California - Santa Cruz"]).option is None


def test_an_unknown_institution_is_not_guessed():
    found = match_choice("school", "Northwind Polytechnic", ["Northwind Institute", "Example State University"])
    assert found.option is None
    stored = {"institution": "Northwind Polytechnic"}
    assert match_choice("school", stored["institution"], ["Northwind Polytechnic"]).option == "Northwind Polytechnic"
    assert stored["institution"] == "Northwind Polytechnic"


def test_two_equivalent_school_options_stay_for_review():
    options = ["University of California, Santa Cruz", "UC Santa Cruz"]
    found = match_choice("school", "UCSC", options)
    assert found.option is None
    assert "More than one listed choice" in found.explanation


def test_degree_abbreviations_keep_type_and_level_apart():
    assert match_choice("degree", "B.S.", ["Bachelor of Science"], "Degree").option == "Bachelor of Science"
    assert match_choice("degree", "B.A.", ["Bachelor of Arts"], "Degree type").option == "Bachelor of Arts"
    assert match_choice("degree", "M.S.", ["Master of Science"], "Degree").option == "Master of Science"
    assert match_choice("degree", "M.A.", ["Master of Arts"], "Degree").option == "Master of Arts"
    assert match_choice("degree", "Ph.D.", ["Doctor of Philosophy"], "Degree").option == "Doctor of Philosophy"
    assert match_choice("degree", "B.S.", ["Bachelor of Arts"], "Degree").option is None
    assert match_choice("degree", "B.S.", ["Bachelor's Degree"], "Degree").option is None
    assert match_choice("degree", "B.S.", ["Bachelor's Degree"], "Highest level of education").option == "Bachelor's Degree"
    assert match_choice("degree", "B.A.", ["Bachelor's Degree"], "Education level").option == "Bachelor's Degree"
    assert match_choice("degree", "M.S.", ["Master's Degree"], "Degree level").option == "Master's Degree"
    level_options = ["Bachelor of Science", "Bachelor's Degree"]
    ambiguous = match_choice("degree", "B.S.", level_options, "Highest level of education")
    assert ambiguous.option is None
    assert "More than one listed choice" in ambiguous.explanation


def test_a_major_does_not_match_a_nearby_name():
    found = match_choice("discipline", "Computer Science", ["Computer Engineering", "Computer Science"])
    assert found.option == "Computer Science"
    assert match_choice("discipline", "Computer Science", ["Computer Engineering"]).option is None


def test_the_plan_uses_the_employer_option_and_keeps_the_fact():
    fact = _education("University of California, Santa Cruz", "B.S.")
    profile = ProfileView(candidate_id=7, full_name="Ada Lovelace", email="ada@example.com")
    form = _form(
        """
        <label for="school">School</label>
        <select id="school" name="school">
          <option>University of California - Santa Cruz</option>
          <option>University of California - Berkeley</option>
        </select>
        <label for="degree">Degree</label>
        <select id="degree" name="degree"><option>Bachelor of Science</option><option>Bachelor of Arts</option></select>
        <label for="major">Major</label>
        <select id="major" name="major"><option>Computer Engineering</option><option>Computer Science</option></select>
        """
    )
    plan = plan_autofill(URL, form, [fact], profile, Materials())
    ready = {item.field_id: item for item in plan.ready}
    assert ready["school"].proposed_value == "University of California - Santa Cruz"
    assert "verified school" in ready["school"].match_note
    assert ready["degree"].proposed_value == "Bachelor of Science"
    assert ready["major"].proposed_value == "Computer Science"
    assert fact.fact_value["institution"] == "University of California, Santa Cruz"
    assert fact.fact_value["degree"] == "B.S."
