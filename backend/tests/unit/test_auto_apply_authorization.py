"""Auto-Apply stays off until the user opts in, and a permitted decision never submits."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.auto_apply.authorization import (
    AUTOMATIC_SUBMISSION,
    AutoApplySettings,
    JobAuthorizationView,
    UsageCounts,
    decide,
    default_settings,
)

NOW = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)


def _grant(**overrides) -> AutoApplySettings:
    values = dict(
        enabled=True,
        acknowledged=True,
        expires_at=NOW + timedelta(days=7),
        job_categories=("swe_backend",),
        employment_types=("internship",),
        locations=("Santa Cruz, CA",),
        min_match_score=70,
        max_per_day=5,
        max_per_session=2,
        resume_ids=(4,),
    )
    values.update(overrides)
    return AutoApplySettings(**values)


def _job(**overrides) -> JobAuthorizationView:
    values = dict(
        provider="greenhouse",
        role_category="swe_backend",
        employment_type="internship",
        locations=("Santa Cruz, CA",),
        remote=False,
        match_score=80,
        eligibility="eligible",
        resume_id=4,
        resume_approved=True,
        readiness_status="ready_to_submit",
        failed_checks=(),
        application_status="ready_to_submit",
    )
    values.update(overrides)
    return JobAuthorizationView(**values)


def _counts(**overrides) -> UsageCounts:
    values = dict(submitted_today=0, submitted_this_session=0)
    values.update(overrides)
    return UsageCounts(**values)


def test_auto_apply_is_disabled_by_default():
    decision = decide(default_settings(), _job(), _counts(), NOW)
    assert decision.permitted is False
    assert decision.submits is False
    assert decision.reasons == ("Auto-Apply is off.",)


def test_explicit_acknowledgement_is_required():
    decision = decide(_grant(acknowledged=False), _job(), _counts(), NOW)
    assert decision.permitted is False
    assert "Auto-Apply has not been explicitly acknowledged." in decision.reasons


def test_expired_authorization_is_not_permitted():
    decision = decide(_grant(expires_at=NOW - timedelta(minutes=1)), _job(), _counts(), NOW)
    assert decision.permitted is False
    assert decision.reasons == ("The authorization has expired.",)


def test_matching_greenhouse_scope_is_permitted_without_submitting():
    decision = decide(_grant(), _job(), _counts(), NOW)
    assert decision.permitted is True
    assert decision.submits is False
    assert decision.reasons == ()
    assert AUTOMATIC_SUBMISSION is False


def test_category_employment_type_and_location_must_match():
    category = decide(_grant(), _job(role_category="swe_frontend"), _counts(), NOW)
    employment = decide(_grant(), _job(employment_type="full_time"), _counts(), NOW)
    location = decide(_grant(), _job(locations=("Seattle, WA",)), _counts(), NOW)
    remote = decide(_grant(locations=("Remote",)), _job(locations=(), remote=True), _counts(), NOW)
    nearby = decide(_grant(), _job(locations=("Santa Cruz",)), _counts(), NOW)
    assert "authorized categories" in category.reasons[0]
    assert "authorized types" in employment.reasons[0]
    assert "authorized locations" in location.reasons[0]
    assert nearby.permitted is False
    assert remote.permitted is True
    assert remote.submits is False


def test_match_score_must_reach_the_threshold():
    low = decide(_grant(), _job(match_score=69), _counts(), NOW)
    missing = decide(_grant(), _job(match_score=None), _counts(), NOW)
    exact = decide(_grant(), _job(match_score=70), _counts(), NOW)
    assert low.permitted is False
    assert missing.permitted is False
    assert exact.permitted is True
    assert exact.submits is False


def test_daily_and_session_limits_stop_authorization():
    daily = decide(_grant(), _job(), _counts(submitted_today=5), NOW)
    session = decide(_grant(), _job(), _counts(submitted_this_session=2), NOW)
    under = decide(_grant(), _job(), _counts(submitted_today=4, submitted_this_session=1), NOW)
    assert "daily application limit" in daily.reasons[0]
    assert "session application limit" in session.reasons[0]
    assert under.permitted is True
    assert under.submits is False


def test_revocation_prevents_authorization():
    decision = decide(_grant(enabled=False), _job(), _counts(), NOW)
    assert decision.permitted is False
    assert decision.reasons == ("Auto-Apply is off.",)


def test_unapproved_resume_is_rejected():
    missing = decide(_grant(), _job(resume_approved=False), _counts(), NOW)
    other = decide(_grant(), _job(resume_id=9), _counts(), NOW)
    assert missing.permitted is False
    assert other.permitted is False
    assert "approved profile" in missing.reasons[0]


def test_unknown_or_ineligible_status_is_rejected():
    unknown = decide(_grant(), _job(eligibility="unknown"), _counts(), NOW)
    ineligible = decide(_grant(), _job(eligibility="ineligible"), _counts(), NOW)
    graduation = decide(
        _grant(),
        _job(readiness_status="needs_review", failed_checks=("graduation",)),
        _counts(),
        NOW,
    )
    assert unknown.reasons == ("Eligibility is unknown.",)
    assert ineligible.reasons == ("The candidate is not eligible.",)
    assert "not eligible" in graduation.reasons[0]


@pytest.mark.parametrize(
    ("check", "phrase"),
    [
        ("required_fields", "incomplete"),
        ("approved_answers", "unapproved"),
        ("sensitive_questions", "sensitive or legal"),
        ("verification_challenge", "CAPTCHA or MFA"),
        ("already_submitted", "already been submitted"),
    ],
)
def test_failed_readiness_checks_are_rejected(check, phrase):
    decision = decide(
        _grant(),
        _job(readiness_status="needs_review", failed_checks=(check,)),
        _counts(),
        NOW,
    )
    assert decision.permitted is False
    assert phrase in decision.reasons[0]


def test_duplicate_and_unresolved_applications_are_rejected():
    submitted = decide(_grant(), _job(application_status="submitted"), _counts(), NOW)
    unknown = decide(_grant(), _job(application_status="confirmation_unknown"), _counts(), NOW)
    assert submitted.permitted is False
    assert "already been submitted" in submitted.reasons[0]
    assert "confirmation is unresolved" in unknown.reasons[0]


def test_unsupported_job_boards_are_rejected():
    lever = decide(_grant(), _job(provider="lever"), _counts(), NOW)
    ashby = decide(_grant(), _job(provider="ashby"), _counts(), NOW)
    assert lever.permitted is False
    assert ashby.permitted is False
    assert "Greenhouse only" in lever.reasons[0]


def test_a_permitted_decision_does_not_call_submit(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("submit was called")

    monkeypatch.setattr("app.autofill.sessions.submit_session", boom)
    decision = decide(_grant(), _job(), _counts(), NOW)
    assert decision.permitted is True
    assert decision.submits is False
