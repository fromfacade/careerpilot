"""Decide whether a filled application is ready for a later submission step.

This module does not open a browser, click Submit, or store an application.
Unknown eligibility is not treated as eligible. A passing result only means
every checked requirement was verified. CareerPilot still does not submit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CONFIRMATION = (
    "thank you for applying",
    "application has been submitted",
    "your application has been received",
    "we have received your application",
)
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class EligibilityReason:
    rule: str
    result: str
    detail: str


@dataclass(frozen=True)
class FieldView:
    field_id: str
    label: str
    required: bool | None
    bucket: str
    existing_value: str | None = None
    uncertainty: str | None = None


@dataclass(frozen=True)
class AnswerView:
    field_id: str
    label: str
    required: bool | None
    bucket: str
    existing_value: str | None = None
    uncertainty: str | None = None


@dataclass(frozen=True)
class OutcomeView:
    field_id: str
    status: str
    detail: str


@dataclass
class ReadinessView:
    employment_type: str = "unknown"
    eligibility: list[EligibilityReason] = field(default_factory=list)
    work_authorization_status: str = "unknown"
    sponsorship: str = "unknown"
    fields: list[FieldView] = field(default_factory=list)
    answers: list[AnswerView] = field(default_factory=list)
    answers_rewritten: bool = False
    resume_field_present: bool = False
    resume_approved: bool = False
    resume_reason: str = ""
    resume_status: str = ""
    resume_detail: str = ""
    fill_attempted: bool = False
    included_field_ids: set[str] = field(default_factory=set)
    outcomes: list[OutcomeView] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    identity_matches: bool = False
    identity_detail: str = ""
    form_found: bool = False
    already_submitted: bool | None = None


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    status: str
    detail: str


@dataclass
class ReadinessResult:
    status: str
    checks: list[ReadinessCheck] = field(default_factory=list)


def submission_state(html: str, form_found: bool) -> bool | None:
    """True when the page says the application was received, False when the form is still open."""
    visible = _STYLE.sub(" ", _SCRIPT.sub(" ", html or ""))
    text = " ".join(_TAG.sub(" ", visible).casefold().split())
    if any(phrase in text for phrase in _CONFIRMATION):
        return True
    if form_found:
        return False
    return None


def assess_readiness(view: ReadinessView) -> ReadinessResult:
    checks = [
        _graduation(view),
        _work_authorization(view),
        _required_fields(view),
        _resume(view),
        _answers(view),
        _sensitive(view),
        _challenge(view),
        _identity(view),
        _submitted(view),
    ]
    status = "ready_to_submit" if all(item.status == "passed" for item in checks) else "needs_review"
    return ReadinessResult(status=status, checks=checks)


def _graduation(view: ReadinessView) -> ReadinessCheck:
    kind = (view.employment_type or "unknown").casefold()
    if kind in {"full_time", "contract"}:
        return ReadinessCheck(
            "graduation",
            "passed",
            "This role is not an internship or new-grad posting, so the graduation window was not required.",
        )
    if kind not in {"internship", "new_grad"}:
        return ReadinessCheck(
            "graduation",
            "needs_review",
            "The job type is unknown, so graduation eligibility could not be verified.",
        )
    reason = next((item for item in view.eligibility if item.rule == "graduation_timing"), None)
    if reason is None or reason.result != "eligible":
        detail = reason.detail if reason else "Graduation eligibility was not assessed."
        return ReadinessCheck("graduation", "needs_review", detail)
    return ReadinessCheck("graduation", "passed", reason.detail)


def _work_authorization(view: ReadinessView) -> ReadinessCheck:
    if (view.work_authorization_status or "unknown").casefold() == "unknown":
        return ReadinessCheck(
            "work_authorization",
            "needs_review",
            "Work authorization is not set on the candidate profile, so it was not treated as eligible.",
        )
    if (view.sponsorship or "unknown").casefold() == "unknown":
        return ReadinessCheck(
            "work_authorization",
            "needs_review",
            "Sponsorship need is not set on the candidate profile, so it was not treated as eligible.",
        )
    reason = next((item for item in view.eligibility if item.rule == "work_authorization"), None)
    if reason is None or reason.result != "eligible":
        detail = reason.detail if reason else "Work authorization was not assessed."
        return ReadinessCheck("work_authorization", "needs_review", detail)
    return ReadinessCheck("work_authorization", "passed", reason.detail)


def _required_fields(view: ReadinessView) -> ReadinessCheck:
    problems: list[str] = []
    outcomes = {item.field_id: item for item in view.outcomes}
    for field in view.fields:
        if field.required is not True or field.bucket == "sensitive":
            continue
        label = field.label or field.field_id
        if field.bucket in {"missing_required", "clarification", "unsupported"}:
            problems.append(f"{label}: {field.uncertainty or 'This required field is not ready to fill.'}")
            continue
        if field.existing_value:
            continue
        if not view.fill_attempted:
            problems.append(f"{label} has not been filled yet.")
            continue
        if field.field_id not in view.included_field_ids:
            problems.append(f"{label} was excluded from the fill.")
            continue
        outcome = outcomes.get(field.field_id)
        if outcome is None or outcome.status not in {"filled", "preserved"}:
            detail = outcome.detail if outcome else "The field was not filled."
            problems.append(f"{label}: {detail}")
    if problems:
        return ReadinessCheck("required_fields", "needs_review", " ".join(problems))
    return ReadinessCheck("required_fields", "passed", "Every required field was filled or already had a value.")


def _resume(view: ReadinessView) -> ReadinessCheck:
    if not view.resume_field_present:
        return ReadinessCheck(
            "resume",
            "needs_review",
            "No resume upload was found, so the attachment could not be verified.",
        )
    if not view.resume_approved:
        return ReadinessCheck("resume", "needs_review", view.resume_reason or "The selected resume is not approved.")
    if not view.fill_attempted:
        return ReadinessCheck("resume", "needs_review", "The approved resume has not been attached yet.")
    if view.resume_status != "attached":
        return ReadinessCheck("resume", "needs_review", view.resume_detail or "The resume was not attached.")
    return ReadinessCheck("resume", "passed", view.resume_detail or "The approved resume was attached.")


def _answers(view: ReadinessView) -> ReadinessCheck:
    if view.answers_rewritten:
        return ReadinessCheck(
            "approved_answers",
            "needs_review",
            "An answer was rewritten. Only the approved text can be used.",
        )
    problems: list[str] = []
    for answer in view.answers:
        if answer.required is not True or answer.bucket == "sensitive":
            continue
        label = answer.label or answer.field_id
        if answer.existing_value:
            continue
        if answer.bucket == "matched" and answer.field_id in view.included_field_ids and _filled(view, answer.field_id):
            continue
        if answer.bucket == "matched" and not view.fill_attempted:
            problems.append(f"{label} has an approved answer that has not been entered yet.")
            continue
        if answer.bucket == "matched":
            problems.append(f"{label} has an approved answer that was not used.")
            continue
        problems.append(f"{label}: {answer.uncertainty or 'No approved answer was entered.'}")
    if problems:
        return ReadinessCheck("approved_answers", "needs_review", " ".join(problems))
    return ReadinessCheck("approved_answers", "passed", "Required questions with an exact approved answer were entered.")


def _sensitive(view: ReadinessView) -> ReadinessCheck:
    labels = [
        item.label or item.field_id
        for item in [*view.fields, *view.answers]
        if item.bucket == "sensitive" and not item.existing_value
    ]
    if labels:
        named = ", ".join(labels)
        return ReadinessCheck(
            "sensitive_questions",
            "needs_review",
            f"These sensitive, legal, or demographic questions are still unanswered: {named}.",
        )
    return ReadinessCheck("sensitive_questions", "passed", "No unanswered sensitive, legal, or demographic questions were found.")


def _challenge(view: ReadinessView) -> ReadinessCheck:
    if any(item in {"captcha", "mfa"} for item in view.blockers):
        return ReadinessCheck(
            "verification_challenge",
            "needs_review",
            "A CAPTCHA or sign-in challenge is active. CareerPilot will not continue past it.",
        )
    return ReadinessCheck("verification_challenge", "passed", "No active CAPTCHA or sign-in challenge was found.")


def _identity(view: ReadinessView) -> ReadinessCheck:
    if not view.identity_matches:
        return ReadinessCheck(
            "job_identity",
            "needs_review",
            view.identity_detail or "The open page is not the Greenhouse job for this preparation.",
        )
    return ReadinessCheck("job_identity", "passed", "The open page is the Greenhouse job selected for this preparation.")


def _submitted(view: ReadinessView) -> ReadinessCheck:
    if view.already_submitted is True:
        return ReadinessCheck(
            "already_submitted",
            "needs_review",
            "The employer page shows this application was already submitted.",
        )
    if view.already_submitted is None:
        return ReadinessCheck(
            "already_submitted",
            "needs_review",
            "CareerPilot could not verify that this application is still unsubmitted.",
        )
    return ReadinessCheck("already_submitted", "passed", "The application form is still open and has not been submitted.")


def readiness_for_run(run) -> ReadinessResult:
    """Assess the session currently held in memory. This never submits."""
    reasons = [
        EligibilityReason(item["rule"], item["result"], item["detail"])
        for item in getattr(run, "eligibility_reasons", []) or []
    ]
    return assess_readiness(
        view_for_plan(
            getattr(run, "plan", None),
            getattr(run, "result", None),
            employment_type=getattr(run, "employment_type", "unknown"),
            eligibility=reasons,
            work_authorization_status=getattr(run, "work_authorization_status", "unknown"),
            sponsorship=getattr(run, "sponsorship", "unknown"),
            fill_attempted=bool(getattr(run, "fill_attempted", False)),
            included_field_ids=set(getattr(run, "included_field_ids", set()) or set()),
            identity_matches=bool(getattr(run, "identity_matches", False)),
            identity_detail=getattr(run, "identity_detail", ""),
            form_found=bool(getattr(run, "form_found", False)),
            already_submitted=getattr(run, "already_submitted", None),
        )
    )


def view_for_plan(plan, fill=None, **kwargs) -> ReadinessView:
    """Build a readiness view from an autofill plan and an optional fill report."""
    fields: list[FieldView] = []
    answers: list[AnswerView] = []
    blockers: list[str] = []
    resume_field = False
    resume_approved = False
    resume_reason = "No resume was selected."
    form_found = False
    rewritten = False
    if plan is not None:
        blockers = list(plan.blockers)
        form_found = bool(plan.form_found)
        rewritten = bool(plan.answers.answers_rewritten)
        resume_field = bool(plan.resume.field_id)
        resume_approved = bool(plan.resume.approved and plan.resume.eligible_for_attach)
        resume_reason = plan.resume.reason
        for bucket in ("ready", "clarification", "missing_required", "sensitive", "unsupported", "preserve_existing"):
            for item in getattr(plan, bucket):
                fields.append(
                    FieldView(
                        field_id=item.field_id,
                        label=item.label,
                        required=item.required,
                        bucket=bucket,
                        existing_value=item.existing_value,
                        uncertainty=item.uncertainty,
                    )
                )
        for bucket in ("matched", "missing", "ambiguous", "sensitive", "preserved"):
            for item in getattr(plan.answers, bucket):
                answers.append(
                    AnswerView(
                        field_id=item.field_id,
                        label=item.label,
                        required=item.required,
                        bucket=bucket,
                        existing_value=item.existing_value,
                        uncertainty=item.uncertainty,
                    )
                )
    outcomes = []
    resume_status = ""
    resume_detail = ""
    if fill is not None:
        resume_status = fill.resume_status
        resume_detail = fill.resume_detail
        outcomes = [OutcomeView(item.field_id, item.status, item.detail) for item in fill.outcomes]
    return ReadinessView(
        fields=fields,
        answers=answers,
        answers_rewritten=rewritten,
        resume_field_present=resume_field,
        resume_approved=resume_approved,
        resume_reason=resume_reason,
        resume_status=resume_status,
        resume_detail=resume_detail,
        outcomes=outcomes,
        blockers=kwargs.pop("blockers", blockers),
        form_found=kwargs.pop("form_found", form_found),
        **kwargs,
    )


def _filled(view: ReadinessView, field_id: str) -> bool:
    if not view.fill_attempted:
        return False
    return any(item.field_id == field_id and item.status in {"filled", "preserved"} for item in view.outcomes)
