"""Readiness is a review decision. It never authorizes or performs a submission."""

from types import SimpleNamespace

import pytest

from app.autofill.actions import SubmissionBlocked, refuse_submission
from app.autofill.readiness import (
    AnswerView,
    EligibilityReason,
    FieldView,
    OutcomeView,
    ReadinessView,
    assess_readiness,
    readiness_for_run,
    submission_state,
    view_for_plan,
)


def _ready() -> ReadinessView:
    return ReadinessView(
        employment_type="internship",
        eligibility=[
            EligibilityReason("graduation_timing", "eligible", "Graduation is still in the future."),
            EligibilityReason("work_authorization", "eligible", "No sponsorship conflict was found."),
        ],
        work_authorization_status="citizen",
        sponsorship="no",
        fields=[FieldView("email", "Email", True, "ready")],
        fill_attempted=True,
        included_field_ids={"email"},
        outcomes=[OutcomeView("email", "filled", "Verified.")],
        resume_field_present=True,
        resume_approved=True,
        resume_status="attached",
        resume_detail="Attached Ada_Lovelace_Resume.pdf.",
        identity_matches=True,
        form_found=True,
        already_submitted=False,
    )


def _check(view: ReadinessView, code: str):
    result = assess_readiness(view)
    return result, next(item for item in result.checks if item.code == code)


def test_every_verified_check_is_ready_but_does_not_submit():
    result = assess_readiness(_ready())
    assert result.status == "ready_to_submit"
    assert all(item.status == "passed" for item in result.checks)
    with pytest.raises(SubmissionBlocked):
        refuse_submission("submit")


def test_unknown_work_authorization_is_not_treated_as_eligible():
    view = _ready()
    view.work_authorization_status = "unknown"
    view.eligibility[1] = EligibilityReason("work_authorization", "eligible", "Sponsorship is not required.")
    result, check = _check(view, "work_authorization")
    assert result.status == "needs_review"
    assert "not treated as eligible" in check.detail


def test_unknown_sponsorship_is_not_treated_as_eligible():
    view = _ready()
    view.sponsorship = "unknown"
    result, check = _check(view, "work_authorization")
    assert result.status == "needs_review"
    assert "Sponsorship need is not set" in check.detail


def test_ineligible_sponsorship_needs_review():
    view = _ready()
    view.sponsorship = "yes"
    view.eligibility[1] = EligibilityReason(
        "work_authorization",
        "ineligible",
        "The posting says it does not sponsor, and the profile requires sponsorship.",
    )
    result, check = _check(view, "work_authorization")
    assert result.status == "needs_review"
    assert "does not sponsor" in check.detail


def test_unknown_graduation_needs_review():
    view = _ready()
    view.eligibility[0] = EligibilityReason("graduation_timing", "unknown", "Graduation date is missing.")
    result, check = _check(view, "graduation")
    assert result.status == "needs_review"
    assert check.detail == "Graduation date is missing."


def test_unknown_job_type_cannot_verify_graduation():
    view = _ready()
    view.employment_type = "unknown"
    result, check = _check(view, "graduation")
    assert result.status == "needs_review"
    assert "job type is unknown" in check.detail


def test_full_time_role_does_not_require_the_internship_window():
    view = _ready()
    view.employment_type = "full_time"
    view.eligibility = [view.eligibility[1]]
    result, check = _check(view, "graduation")
    assert check.status == "passed"
    assert result.status == "ready_to_submit"


def test_missing_required_field_needs_review():
    view = _ready()
    view.fields.append(
        FieldView("phone", "Phone", True, "missing_required", uncertainty="No verified phone number is available.")
    )
    result, check = _check(view, "required_fields")
    assert result.status == "needs_review"
    assert "No verified phone number is available." in check.detail


def test_required_field_not_filled_yet_needs_review():
    view = _ready()
    view.fill_attempted = False
    result, check = _check(view, "required_fields")
    assert result.status == "needs_review"
    assert "Email has not been filled yet." in check.detail


def test_failed_required_fill_needs_review():
    view = _ready()
    view.outcomes = [OutcomeView("email", "failed", "The value did not stay on the form.")]
    result, check = _check(view, "required_fields")
    assert result.status == "needs_review"
    assert "did not stay" in check.detail


def test_unapproved_resume_needs_review():
    view = _ready()
    view.resume_approved = False
    view.resume_reason = "The selected resume is not approved."
    result, check = _check(view, "resume")
    assert result.status == "needs_review"
    assert check.detail == "The selected resume is not approved."


def test_resume_not_attached_needs_review():
    view = _ready()
    view.resume_status = "failed"
    view.resume_detail = "The file was not accepted."
    result, check = _check(view, "resume")
    assert result.status == "needs_review"
    assert check.detail == "The file was not accepted."


def test_missing_resume_upload_cannot_be_verified():
    view = _ready()
    view.resume_field_present = False
    result, check = _check(view, "resume")
    assert result.status == "needs_review"
    assert "could not be verified" in check.detail


def test_required_approved_answer_that_was_not_used_needs_review():
    view = _ready()
    view.answers = [AnswerView("why", "Why this role?", True, "matched")]
    result, check = _check(view, "approved_answers")
    assert result.status == "needs_review"
    assert "was not used" in check.detail


def test_ambiguous_required_answer_needs_review():
    view = _ready()
    view.answers = [
        AnswerView("why", "Why this role?", True, "ambiguous", uncertainty="More than one approved answer could match.")
    ]
    result, check = _check(view, "approved_answers")
    assert result.status == "needs_review"
    assert "More than one approved answer" in check.detail


def test_optional_ambiguous_answer_does_not_block_readiness():
    view = _ready()
    view.answers = [AnswerView("why", "Why this role?", False, "ambiguous", uncertainty="Several answers are close.")]
    assert assess_readiness(view).status == "ready_to_submit"


def test_unanswered_sensitive_question_needs_review():
    view = _ready()
    view.fields.append(FieldView("eeo", "Gender", True, "sensitive"))
    result, check = _check(view, "sensitive_questions")
    assert result.status == "needs_review"
    assert "Gender" in check.detail


def test_sensitive_question_with_an_existing_answer_does_not_block():
    view = _ready()
    view.fields.append(FieldView("eeo", "Gender", True, "sensitive", existing_value="Prefer not to say"))
    result, check = _check(view, "sensitive_questions")
    assert check.status == "passed"
    assert result.status == "ready_to_submit"


def test_captcha_or_mfa_needs_review():
    view = _ready()
    view.blockers = ["captcha"]
    result, check = _check(view, "verification_challenge")
    assert result.status == "needs_review"
    assert "CAPTCHA" in check.detail
    view.blockers = ["mfa"]
    assert assess_readiness(view).status == "needs_review"


def test_different_greenhouse_job_needs_review():
    view = _ready()
    view.identity_matches = False
    view.identity_detail = "The open form is stripe/2, but the selected preparation is stripe/1."
    result, check = _check(view, "job_identity")
    assert result.status == "needs_review"
    assert "stripe/2" in check.detail


def test_already_submitted_page_needs_review():
    view = _ready()
    view.already_submitted = True
    result, check = _check(view, "already_submitted")
    assert result.status == "needs_review"
    assert "already submitted" in check.detail


def test_unknown_submission_outcome_needs_review():
    view = _ready()
    view.already_submitted = None
    result, check = _check(view, "already_submitted")
    assert result.status == "needs_review"
    assert "could not verify" in check.detail


def test_confirmation_text_is_read_from_the_page_and_not_from_scripts():
    assert submission_state("<html><body><p>Thank you for applying.</p></body></html>", False) is True
    assert submission_state("<script>thank you for applying</script><form id='application'></form>", True) is False
    assert submission_state("<html><body>Loading</body></html>", False) is None


def test_plan_view_keeps_missing_fields_and_blockers():
    field = SimpleNamespace(
        field_id="phone",
        label="Phone",
        required=True,
        existing_value=None,
        uncertainty="No verified phone number is available.",
    )
    plan = SimpleNamespace(
        blockers=["mfa"],
        form_found=True,
        resume=SimpleNamespace(field_id="resume", approved=False, eligible_for_attach=False, reason="Not approved."),
        answers=SimpleNamespace(
            answers_rewritten=False, matched=[], missing=[], ambiguous=[], sensitive=[], preserved=[]
        ),
        ready=[],
        clarification=[],
        missing_required=[field],
        sensitive=[],
        unsupported=[],
        preserve_existing=[],
    )
    view = view_for_plan(
        plan,
        employment_type="internship",
        eligibility=_ready().eligibility,
        work_authorization_status="citizen",
        sponsorship="no",
        fill_attempted=True,
        included_field_ids=set(),
        identity_matches=True,
        already_submitted=False,
    )
    result = assess_readiness(view)
    assert result.status == "needs_review"
    assert any("phone number" in item.detail for item in result.checks)
    assert any(item.code == "verification_challenge" and item.status == "needs_review" for item in result.checks)


def test_session_without_a_plan_needs_review():
    run = SimpleNamespace(
        plan=None,
        result=None,
        eligibility_reasons=[],
        employment_type="unknown",
        work_authorization_status="unknown",
        sponsorship="unknown",
        fill_attempted=False,
        included_field_ids=set(),
        identity_matches=False,
        identity_detail="",
        form_found=False,
        already_submitted=None,
    )
    assert readiness_for_run(run).status == "needs_review"
