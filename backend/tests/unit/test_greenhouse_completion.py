"""Completion counts verified fields once and ignores hidden or failed controls."""

from app.autofill.browser_fill import FieldOutcome, FillReport
from app.autofill.completion import completion_for
from app.autofill.mapping import FactView, ProfileView, plan_autofill
from app.autofill.materials import AnswerView, Materials

URL = "https://boards.greenhouse.io/northwind/jobs/15"
FORM = """
<form id="application">
  <label for="email">Email *</label>
  <input id="email" name="email" type="email" required>
  <label for="phone">Phone</label>
  <input id="phone" name="phone" type="tel">
  <label for="city">City</label>
  <input id="city" name="city" value="Austin, TX">
  <label for="year">Graduation year *</label>
  <select id="year" name="year" required><option>2026</option><option>2027</option></select>
  <label for="one">Why this role?</label>
  <textarea id="one" name="one"></textarea>
  <label for="two">Why this role?</label>
  <textarea id="two" name="two"></textarea>
  <label for="work">Work authorization *</label>
  <select id="work" name="work" required><option>Yes</option><option>No</option></select>
  <div hidden>
    <label for="ghost">Employment type</label>
    <select id="ghost" name="ghost"><option>Internship</option></select>
  </div>
</form>
"""


def test_completion_separates_verified_fills_from_manual_work():
    education = FactView(
        id=4,
        fact_type="education",
        fact_key="school",
        fact_value={"end_date": "2027-05"},
        identity_key="education|example",
        status="active",
        verification_status="verified",
    )
    profile = ProfileView(
        candidate_id=7,
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="555-0100",
        location="Austin, TX",
    )
    answer = AnswerView(
        id=2,
        question="Why this role?",
        answer_text="I want to build the payments ledger.",
        approval_status="approved",
        origin="manual",
        category="motivation",
        source="job_specific",
    )
    plan = plan_autofill(URL, FORM, [education], profile, Materials(job_answers=[answer]))
    report = FillReport(
        outcomes=[
            FieldOutcome("email", "Email", "filled", "Verified."),
            FieldOutcome("phone", "Phone", "failed", "The field could not be filled."),
            FieldOutcome("city", "City", "preserved", "The existing value was kept."),
            FieldOutcome("year", "Graduation year", "filled", "Verified."),
            FieldOutcome("one", "Why this role?", "stale", "More than one field asks this question, so it was left for review."),
            FieldOutcome("two", "Why this role?", "stale", "More than one field asks this question, so it was left for review."),
        ],
        submitted=False,
    )
    metrics = completion_for(plan, report)
    assert metrics.total == 6
    assert metrics.autofilled == 2
    assert metrics.already_completed == 1
    assert metrics.manual == 3
    assert metrics.required_unanswered == 1
    assert metrics.percent == 50
    assert "ghost" not in {item.field_id for item in plan.ready + plan.unsupported + plan.answers.missing}
    assert report.submitted is False


def test_an_interrupted_fill_does_not_count_attempted_fields():
    profile = ProfileView(candidate_id=7, email="ada@example.com")
    plan = plan_autofill(URL, FORM, [], profile, Materials())
    report = FillReport(
        outcomes=[FieldOutcome("email", "Email", "failed", "The browser left the Greenhouse application page.")],
        stopped="The browser left the Greenhouse application page.",
        submitted=False,
    )
    metrics = completion_for(plan, report)
    assert metrics.autofilled == 0
    assert report.submitted is False
