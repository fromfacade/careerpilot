"""Draft Greenhouse answers only when nothing approved applies. Gemini is mocked."""

from __future__ import annotations

import pytest

from app.ai.mock import MockAnswerProvider
from app.ai.types import GenerationRequest
from app.autofill.actions import decide_fill, reviewed_fields
from app.autofill.drafting import draft_action, limit_text
from app.core.exceptions import AIProviderError, ValidationError
from app.models.answer import ApplicationAnswer
from app.models.canonical import CanonicalFact
from app.models.candidate import Candidate
from app.models.enums import (
    AnswerCategory,
    AnswerStatus,
    CanonicalFactStatus,
    FactType,
    FactVerificationStatus,
    PreparationAnswerOrigin,
    PreparationItemStatus,
)
from app.models.preparation import ApplicationPreparation, ApplicationPreparationAnswer
from app.services import answer_service, preparation_service, writing_style_service
from app.services.autofill_service import build_plan
from app.services.greenhouse_drafts import ensure_form_drafts, regenerate_form_draft

URL = "https://boards.greenhouse.io/northwind/jobs/15"
PROJECT = "Describe a technical project you built."
WHY = "Why are you interested in this role?"


def test_draft_policy_skips_sensitive_and_factual_questions():
    assert draft_action("", "Describe a technical project you built.") == "generate"
    assert draft_action("", "Describe your relevant experience.") == "generate"
    assert draft_action("", "Why do you want to work at Northwind?") == "generate"
    assert draft_action("", "Explain your interest in Python.") == "generate"
    assert draft_action("", "Years of experience") == "skip"
    assert draft_action("", "Cumulative GPA") == "fact"
    assert draft_action("", "Expected graduation") == "fact"
    assert draft_action("", "When can you start?") == "fact"
    assert draft_action("", "Are you authorized to work in the United States?") == "manual"
    assert draft_action("", "Will you require visa sponsorship?") == "manual"
    clipped, shortened = limit_text("one two three four", "Answer in 2 words.")
    assert shortened is True
    assert clipped == "one two"
    clipped, shortened = limit_text("abcdef ghij", "Limit: 6 characters.")
    assert shortened is True
    assert len(clipped) <= 6


def _candidate(db) -> Candidate:
    row = Candidate(full_name="Ada Lovelace", email="ada.draft@example.com")
    db.add(row)
    db.flush()
    return row


def _fact(db, candidate: Candidate) -> CanonicalFact:
    row = CanonicalFact(
        candidate_id=candidate.id,
        fact_type=FactType.PROJECT,
        fact_key="Lantern",
        fact_value={"name": "Lantern", "detail": "Built a lantern API in Python."},
        identity_key="project|lantern",
        content_fingerprint="fp-lantern",
        status=CanonicalFactStatus.ACTIVE,
        verification_status=FactVerificationStatus.VERIFIED,
    )
    db.add(row)
    db.flush()
    return row


def _preparation(db, candidate: Candidate) -> ApplicationPreparation:
    row = ApplicationPreparation(
        candidate_id=candidate.id,
        snapshot_job_title="Backend Intern",
        snapshot_employer="Northwind",
        snapshot_description="Build a payments ledger for merchants.",
        snapshot_apply_url=URL,
        analysis={},
        match_report={},
        tailored_resume={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _form(*fields: str) -> str:
    parts = ['<form id="application">']
    for index, label in enumerate(fields, start=1):
        parts.append(f'<label for="q{index}">{label}</label><textarea id="q{index}" name="q{index}"></textarea>')
    parts.append("</form>")
    return "".join(parts)


def _style(db, candidate: Candidate) -> None:
    profile = writing_style_service.get_or_create_profile(db, candidate)
    profile.additional_instructions = "mention lanterns plainly"
    db.commit()


def _draft(db, candidate, preparation, label: str, provider) -> None:
    plan = build_plan(db, candidate, URL, _form(label), preparation.id)
    ensure_form_drafts(db, candidate, preparation.id, plan, provider=provider)


def test_no_match_saves_an_unapproved_grounded_draft(db_session):
    candidate = _candidate(db_session)
    fact = _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    _style(db_session, candidate)
    provider = MockAnswerProvider("I built the Lantern API.")
    _draft(db_session, candidate, preparation, PROJECT, provider)

    request = provider.calls[0]
    assert isinstance(request, GenerationRequest)
    assert "Use ONLY the verified personal facts" in request.system_instruction
    assert "mention lanterns plainly" in request.style_guidance
    assert "Northwind" in request.question
    assert "payments ledger" in request.facts_block
    assert len(provider.calls) == 1

    plan = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    item = plan.answers.missing[0]
    assert item.match_kind == "no_match"
    assert item.proposed_text == "I built the Lantern API."
    assert item.eligible_for_fill is False
    assert item.approval_status == "draft"
    assert item.supporting_facts == [f"project: {fact.fact_key}"]
    assert "q1" not in reviewed_fields(plan)
    blocked = decide_fill(reviewed_fields(plan), plan, included={"q1"}, overwrite=set(), attach_resume=False)
    assert blocked.actions == []
    assert blocked.stale == ["q1"]

    _draft(db_session, candidate, preparation, PROJECT, provider)
    assert len(provider.calls) == 1
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert len(saved.answers) == 1
    library = db_session.get(ApplicationAnswer, saved.answers[0].source_answer_id)
    assert library.generation_metadata["style_profile_id"]
    assert library.generation_metadata["employer"] == "Northwind"
    assert library.is_reusable is False


def test_an_approved_answer_is_not_drafted_again(db_session):
    candidate = _candidate(db_session)
    preparation = _preparation(db_session, candidate)
    preparation.answers.append(
        ApplicationPreparationAnswer(
            question=PROJECT,
            answer_text="I built the Lantern API.",
            category=AnswerCategory.EXPERIENCE,
            origin=PreparationAnswerOrigin.REUSED,
            status=PreparationItemStatus.APPROVED,
        )
    )
    db_session.commit()
    provider = MockAnswerProvider("A second draft that should not exist.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    assert provider.calls == []
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert len(saved.answers) == 1
    assert saved.answers[0].answer_text == "I built the Lantern API."


def test_an_uncertain_match_does_not_get_a_competing_draft(db_session):
    candidate = _candidate(db_session)
    preparation = _preparation(db_session, candidate)
    answer_service.create_answer(
        db_session,
        candidate,
        question="Why do you want to work at Stripe?",
        answer_text="I want to work on Stripe payments.",
        category=AnswerCategory.INTEREST,
        status=AnswerStatus.APPROVED,
        is_reusable=True,
    )
    label = "Why do you want to work at Northwind?"
    plan = build_plan(db_session, candidate, URL, _form(label), preparation.id)
    assert plan.answers.ambiguous
    assert plan.answers.ambiguous[0].match_kind == "uncertain_match"
    provider = MockAnswerProvider("I want to join Northwind.")
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert provider.calls == []
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert saved.answers == []


def test_missing_facts_are_flagged_without_calling_the_model(db_session):
    candidate = _candidate(db_session)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I built a project that does not exist.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    assert provider.calls == []
    plan = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    item = plan.answers.missing[0]
    assert item.proposed_text is None
    assert item.eligible_for_fill is False
    assert "No verified project facts" in (item.uncertainty or "")


def test_factual_questions_are_not_invented(db_session):
    candidate = _candidate(db_session)
    preparation = _preparation(db_session, candidate)
    label = "Cumulative GPA"
    html = """
    <form id="application">
      <label for="gpa">Cumulative GPA</label>
      <input id="gpa" name="gpa" type="text">
    </form>
    """
    provider = MockAnswerProvider("3.96")
    plan = build_plan(db_session, candidate, URL, html, preparation.id)
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert provider.calls == []
    shown = build_plan(db_session, candidate, URL, html, preparation.id)
    item = next(answer for answer in shown.answers.missing if answer.label == label)
    assert item.eligible_for_fill is False
    assert "GPA" in (item.uncertainty or "")
    assert "will not guess" in (item.uncertainty or "")
    with pytest.raises(ValidationError):
        regenerate_form_draft(db_session, candidate, preparation.id, label, provider=provider)


def test_sensitive_questions_are_not_drafted(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    html = f"""
    <form id="application">
      <label for="project">{PROJECT}</label>
      <textarea id="project" name="project"></textarea>
      <label for="work_auth">Are you authorized to work in the United States?</label>
      <select id="work_auth" name="work_auth" required>
        <option>Yes</option>
        <option>No</option>
      </select>
    </form>
    """
    provider = MockAnswerProvider("I built the Lantern API.")
    plan = build_plan(db_session, candidate, URL, html, preparation.id)
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert len(provider.calls) == 1
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert [item.question for item in saved.answers] == [PROJECT]
    assert any(item.match_kind == "sensitive" for item in plan.answers.sensitive)
    with pytest.raises(ValidationError):
        regenerate_form_draft(
            db_session,
            candidate,
            preparation.id,
            "Are you authorized to work in the United States?",
            provider=provider,
        )


def test_word_and_character_limits_are_applied(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    words = "Describe a technical project you built in 12 words."
    provider = MockAnswerProvider(" ".join(f"word{index}" for index in range(30)))
    _draft(db_session, candidate, preparation, words, provider)
    assert "at most 12 words" in provider.calls[0].question
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert len(saved.answers[0].answer_text.split()) == 12
    assert any("shortened" in note.casefold() for note in saved.answers[0].missing_information)

    short = "Why are you interested in this role? Please answer in 40 characters."
    provider.text = "I want to help Northwind build the payments ledger described in the posting."
    _draft(db_session, candidate, preparation, short, provider)
    fresh = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    interest = next(item for item in fresh.answers if item.question == short)
    assert len(interest.answer_text) <= 40


def test_unsupported_claims_must_be_edited_before_approval(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I launched Zephyr in 2019.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    item = saved.answers[0]
    assert item.unsupported_claims
    with pytest.raises(ValidationError):
        preparation_service.update_preparation_answer(
            db_session,
            candidate,
            preparation.id,
            item.id,
            status=PreparationItemStatus.APPROVED,
        )
    preparation_service.update_preparation_answer(
        db_session,
        candidate,
        preparation.id,
        item.id,
        answer_text="I built the Lantern API.",
        status=PreparationItemStatus.APPROVED,
    )
    approved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert approved.answers[0].unsupported_claims == []
    assert approved.answers[0].status is PreparationItemStatus.APPROVED
    library = db_session.get(ApplicationAnswer, approved.answers[0].source_answer_id)
    assert library.status is AnswerStatus.APPROVED
    assert library.is_reusable is True


def test_approval_refreshes_the_plan_and_fills_only_that_answer(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I built the Lantern API.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    preparation_service.update_preparation_answer(
        db_session,
        candidate,
        preparation.id,
        saved.answers[0].id,
        status=PreparationItemStatus.APPROVED,
    )
    plan = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    matched = plan.answers.matched[0]
    assert matched.eligible_for_fill is True
    assert matched.proposed_text == "I built the Lantern API."
    decision = decide_fill(
        reviewed_fields(plan),
        plan,
        included={matched.field_id},
        overwrite=set(),
        attach_resume=False,
    )
    assert [action.field_id for action in decision.actions] == [matched.field_id]
    assert decision.actions[0].value == "I built the Lantern API."

    filled = """
    <form id="application">
      <label for="q1">Describe a technical project you built.</label>
      <textarea id="q1" name="q1">Keep this note.</textarea>
    </form>
    """
    existing = build_plan(db_session, candidate, URL, filled, preparation.id)
    kept = decide_fill(
        reviewed_fields(existing),
        existing,
        included={existing.answers.preserved[0].field_id},
        overwrite=set(),
        attach_resume=False,
    )
    assert kept.actions == []
    assert existing.answers.preserved[0].field_id in kept.preserved


def test_reject_edit_and_regenerate(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I built the Lantern API.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    item = saved.answers[0]
    preparation_service.update_preparation_answer(
        db_session,
        candidate,
        preparation.id,
        item.id,
        answer_text="I built the Lantern API for merchants.",
        status=PreparationItemStatus.DRAFT,
    )
    edited = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert edited.answers[0].answer_text == "I built the Lantern API for merchants."
    preparation_service.update_preparation_answer(
        db_session,
        candidate,
        preparation.id,
        item.id,
        status=PreparationItemStatus.REJECTED,
    )
    rejected = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    assert rejected.answers.missing[0].eligible_for_fill is False
    assert "rejected" in rejected.answers.missing[0].explanation.casefold()

    provider.text = "I maintained the Lantern API."
    regenerate_form_draft(db_session, candidate, preparation.id, PROJECT, provider=provider)
    assert len(provider.calls) == 2
    fresh = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert fresh.answers[0].status is PreparationItemStatus.DRAFT
    assert fresh.answers[0].answer_text == "I maintained the Lantern API."
    assert len(fresh.answers) == 1


def test_a_changed_application_snapshot_refreshes_a_draft_once(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I built the Lantern API.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    preparation.snapshot_description = "Operate the storefront ledger instead."
    db_session.commit()
    provider.text = "I kept the Lantern API running."
    plan = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert len(provider.calls) == 2
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert saved.answers[0].answer_text == "I kept the Lantern API running."
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert len(provider.calls) == 2


def test_a_provider_failure_is_saved_and_not_retried(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)

    class Failing:
        name = "mock"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            raise AIProviderError("unavailable", "network down")

    provider = Failing()
    plan = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    ensure_form_drafts(db_session, candidate, preparation.id, plan, provider=provider)
    assert provider.calls == 1
    shown = build_plan(db_session, candidate, URL, _form(PROJECT), preparation.id)
    assert shown.answers.missing[0].proposed_text is None
    assert "could not be generated" in (shown.answers.missing[0].uncertainty or "")
    assert shown.answers.missing[0].eligible_for_fill is False
    ensure_form_drafts(db_session, candidate, preparation.id, shown, provider=provider)
    assert provider.calls == 1


def test_form_drafts_survive_the_fixed_preparation_question_set(db_session):
    candidate = _candidate(db_session)
    _fact(db_session, candidate)
    preparation = _preparation(db_session, candidate)
    provider = MockAnswerProvider("I built the Lantern API.")
    _draft(db_session, candidate, preparation, PROJECT, provider)
    saved = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    draft_id = saved.answers[0].id
    preparation_service.fill_preparation_answers(
        db_session,
        candidate,
        saved,
        provider=MockAnswerProvider("I want to build backend systems."),
    )
    fresh = preparation_service.get_preparation_or_404(db_session, candidate, preparation.id)
    assert any(item.id == draft_id and item.answer_text == "I built the Lantern API." for item in fresh.answers)
