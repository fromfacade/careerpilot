"""Unit tests for rule-based eligibility checking and match scoring.

These exercise pure business logic (app.services.eligibility_service) with
no network calls. We build real ORM objects via the test database fixture
(db_session) rather than hand-wiring detached SQLAlchemy instances, since
that keeps relationship loading (candidate.role_preferences, etc.) honest
and avoids subtly wrong "fake" object graphs. No HTTP/adapter code is
exercised here.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.candidate import Candidate, CandidateLocationPreference, CandidatePreference, CandidateRolePreference
from app.models.enums import (
    Eligibility,
    EmploymentType,
    JobProvider,
    LocationPreferenceType,
    RemoteType,
    RoleCategory,
    TriState,
    WorkAuthStatus,
)
from app.models.job import Job, JobLocation
from app.models.job_source import Employer, JobSource
from app.services.eligibility_service import assess_eligibility, compute_match_score


def _make_job(
    db,
    *,
    title: str = "Software Engineer",
    role_category: RoleCategory = RoleCategory.SWE_BACKEND,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    remote_type: RemoteType = RemoteType.UNKNOWN,
    description_text: str = "Build great software.",
    locations: list[str] | None = None,
) -> Job:
    employer = Employer(name=f"Employer for {title}")
    db.add(employer)
    db.flush()
    job_source = JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token=f"tok-{title}")
    db.add(job_source)
    db.flush()
    job = Job(
        job_source_id=job_source.id,
        external_id=f"ext-{title}",
        title=title,
        role_category=role_category,
        employment_type=employment_type,
        remote_type=remote_type,
        description_text=description_text,
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/apply",
        content_hash="hash",
        dedupe_key="dedupe",
        raw_payload={},
    )
    db.add(job)
    db.flush()
    for loc in locations or ["San Francisco, CA"]:
        db.add(JobLocation(job_id=job.id, raw_text=loc, is_remote="remote" in loc.lower()))
    db.flush()
    db.refresh(job)
    return job


def _make_candidate(
    db,
    *,
    work_authorization_status: WorkAuthStatus = WorkAuthStatus.UNKNOWN,
    requires_sponsorship: TriState = TriState.UNKNOWN,
    graduation_date: date | None = None,
    email: str = "candidate@example.com",
) -> Candidate:
    candidate = Candidate(
        full_name="Test Candidate",
        email=email,
        work_authorization_status=work_authorization_status,
        requires_sponsorship=requires_sponsorship,
        graduation_date=graduation_date,
    )
    db.add(candidate)
    db.flush()
    db.refresh(candidate)
    return candidate


class TestSponsorshipRule:
    def test_unknown_when_profile_fully_unset(self, db_session):
        candidate = _make_candidate(db_session)
        job = _make_job(db_session)

        eligibility, reasons = assess_eligibility(candidate, job)

        assert eligibility == Eligibility.UNKNOWN
        work_auth_reason = next(r for r in reasons if r["rule"] == "work_authorization")
        assert work_auth_reason["result"] == Eligibility.UNKNOWN.value

    def test_ineligible_when_job_excludes_sponsorship_and_candidate_needs_it(self, db_session):
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.YES)
        job = _make_job(
            db_session, description_text="Great role. We are not able to sponsor work visas for this position."
        )

        eligibility, reasons = assess_eligibility(candidate, job)

        assert eligibility == Eligibility.INELIGIBLE
        work_auth_reason = next(r for r in reasons if r["rule"] == "work_authorization")
        assert work_auth_reason["result"] == Eligibility.INELIGIBLE.value

    def test_eligible_when_candidate_does_not_require_sponsorship(self, db_session):
        candidate = _make_candidate(
            db_session, work_authorization_status=WorkAuthStatus.US_CITIZEN, requires_sponsorship=TriState.NO
        )
        job = _make_job(db_session, description_text="We are not able to sponsor work visas.")

        eligibility, reasons = assess_eligibility(candidate, job)

        work_auth_reason = next(r for r in reasons if r["rule"] == "work_authorization")
        assert work_auth_reason["result"] == Eligibility.ELIGIBLE.value
        # Full-time jobs have no graduation-timing rule, so this is the only reason.
        assert eligibility == Eligibility.ELIGIBLE

    def test_unknown_when_sponsorship_need_unset_but_auth_status_set(self, db_session):
        # work_authorization_status alone being set is not enough to resolve
        # the sponsorship question explicitly.
        candidate = _make_candidate(db_session, work_authorization_status=WorkAuthStatus.VISA_HOLDER)
        job = _make_job(db_session)

        eligibility, reasons = assess_eligibility(candidate, job)

        assert eligibility == Eligibility.UNKNOWN


class TestGraduationTimingRule:
    def test_not_applicable_for_full_time(self, db_session):
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO)
        job = _make_job(db_session, employment_type=EmploymentType.FULL_TIME)

        _, reasons = assess_eligibility(candidate, job)

        assert not any(r["rule"] == "graduation_timing" for r in reasons)

    def test_new_grad_unknown_when_no_graduation_date(self, db_session):
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO, graduation_date=None)
        job = _make_job(db_session, employment_type=EmploymentType.NEW_GRAD)

        eligibility, reasons = assess_eligibility(candidate, job)

        grad_reason = next(r for r in reasons if r["rule"] == "graduation_timing")
        assert grad_reason["result"] == Eligibility.UNKNOWN.value
        assert eligibility == Eligibility.UNKNOWN

    def test_new_grad_ineligible_when_graduation_too_far_out(self, db_session):
        today = date.today()
        far_future = date(today.year + 3, today.month, 1)
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO, graduation_date=far_future)
        job = _make_job(db_session, employment_type=EmploymentType.NEW_GRAD)

        eligibility, reasons = assess_eligibility(candidate, job)

        grad_reason = next(r for r in reasons if r["rule"] == "graduation_timing")
        assert grad_reason["result"] == Eligibility.INELIGIBLE.value
        assert eligibility == Eligibility.INELIGIBLE

    def test_new_grad_eligible_within_window(self, db_session):
        today = date.today()
        near_future = today + timedelta(days=60)
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO, graduation_date=near_future)
        job = _make_job(db_session, employment_type=EmploymentType.NEW_GRAD)

        eligibility, reasons = assess_eligibility(candidate, job)

        grad_reason = next(r for r in reasons if r["rule"] == "graduation_timing")
        assert grad_reason["result"] == Eligibility.ELIGIBLE.value
        assert eligibility == Eligibility.ELIGIBLE

    def test_internship_ineligible_when_already_graduated(self, db_session):
        past = date.today() - timedelta(days=400)
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO, graduation_date=past)
        job = _make_job(db_session, employment_type=EmploymentType.INTERNSHIP)

        eligibility, reasons = assess_eligibility(candidate, job)

        grad_reason = next(r for r in reasons if r["rule"] == "graduation_timing")
        assert grad_reason["result"] == Eligibility.INELIGIBLE.value
        assert eligibility == Eligibility.INELIGIBLE

    def test_internship_eligible_when_still_a_student(self, db_session):
        # Target: graduation Dec 2027, matching the user's actual timeline.
        candidate = _make_candidate(db_session, requires_sponsorship=TriState.NO, graduation_date=date(2027, 12, 1))
        job = _make_job(db_session, employment_type=EmploymentType.INTERNSHIP)

        eligibility, reasons = assess_eligibility(candidate, job)

        grad_reason = next(r for r in reasons if r["rule"] == "graduation_timing")
        assert grad_reason["result"] == Eligibility.ELIGIBLE.value
        assert eligibility == Eligibility.ELIGIBLE

    def test_ineligible_wins_over_unknown(self, db_session):
        # Sponsorship unknown (UNKNOWN) + graduation too far out (INELIGIBLE) => overall INELIGIBLE.
        today = date.today()
        far_future = date(today.year + 3, today.month, 1)
        candidate = _make_candidate(db_session, graduation_date=far_future)  # sponsorship left UNKNOWN
        job = _make_job(db_session, employment_type=EmploymentType.NEW_GRAD)

        eligibility, _ = assess_eligibility(candidate, job)

        assert eligibility == Eligibility.INELIGIBLE


class TestMatchScoring:
    def test_role_match_at_top_priority_scores_full_weight(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(candidate_id=candidate.id, remote_ok=True)
        db_session.add(prefs)
        db_session.add(CandidateRolePreference(candidate_id=candidate.id, role_category=RoleCategory.SWE_BACKEND, priority=0))
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, role_category=RoleCategory.SWE_BACKEND, locations=["Remote"], remote_type=RemoteType.REMOTE)

        score, reasons = compute_match_score(job, candidate.preferences)

        role_reason = next(r for r in reasons if r["factor"] == "role_category")
        assert role_reason["contribution"] == role_reason["weight"] == 40

    def test_role_not_in_preferences_scores_zero_for_that_factor(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(candidate_id=candidate.id, remote_ok=True)
        db_session.add(prefs)
        db_session.add(CandidateRolePreference(candidate_id=candidate.id, role_category=RoleCategory.QA, priority=0))
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, role_category=RoleCategory.SWE_BACKEND)

        _, reasons = compute_match_score(job, candidate.preferences)

        role_reason = next(r for r in reasons if r["factor"] == "role_category")
        assert role_reason["contribution"] == 0

    def test_location_alias_matches_california(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(candidate_id=candidate.id, remote_ok=False)
        db_session.add(prefs)
        db_session.add(
            CandidateLocationPreference(
                candidate_id=candidate.id, label="California", location_type=LocationPreferenceType.STATE, priority=0
            )
        )
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, locations=["San Francisco, CA"], remote_type=RemoteType.ONSITE)

        _, reasons = compute_match_score(job, candidate.preferences)

        location_reason = next(r for r in reasons if r["factor"] == "location")
        assert location_reason["contribution"] == 30

    def test_remote_job_matches_when_candidate_remote_ok(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(candidate_id=candidate.id, remote_ok=True)
        db_session.add(prefs)
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, locations=["Remote - US"], remote_type=RemoteType.REMOTE)

        _, reasons = compute_match_score(job, candidate.preferences)

        location_reason = next(r for r in reasons if r["factor"] == "location")
        assert location_reason["contribution"] == 30
        remote_reason = next(r for r in reasons if r["factor"] == "remote_alignment")
        assert remote_reason["contribution"] == 10

    def test_remote_job_scores_zero_when_candidate_excludes_remote(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(candidate_id=candidate.id, remote_ok=False)
        db_session.add(prefs)
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, locations=["Remote - US"], remote_type=RemoteType.REMOTE)

        _, reasons = compute_match_score(job, candidate.preferences)

        remote_reason = next(r for r in reasons if r["factor"] == "remote_alignment")
        assert remote_reason["contribution"] == 0

    def test_employment_type_match(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(
            candidate_id=candidate.id, remote_ok=True, target_employment_types=[EmploymentType.INTERNSHIP]
        )
        db_session.add(prefs)
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(db_session, employment_type=EmploymentType.INTERNSHIP)

        _, reasons = compute_match_score(job, candidate.preferences)

        et_reason = next(r for r in reasons if r["factor"] == "employment_type")
        assert et_reason["contribution"] == 20

    def test_no_preferences_at_all_still_returns_a_score_in_range(self, db_session):
        candidate = _make_candidate(db_session)
        job = _make_job(db_session)

        score, reasons = compute_match_score(job, None)

        assert 0 <= score <= 100
        assert len(reasons) == 4

    def test_total_score_is_sum_of_contributions_and_bounded(self, db_session):
        candidate = _make_candidate(db_session)
        prefs = CandidatePreference(
            candidate_id=candidate.id, remote_ok=True, target_employment_types=[EmploymentType.INTERNSHIP]
        )
        db_session.add(prefs)
        db_session.add(CandidateRolePreference(candidate_id=candidate.id, role_category=RoleCategory.SWE_BACKEND, priority=0))
        db_session.add(
            CandidateLocationPreference(
                candidate_id=candidate.id, label="Remote", location_type=LocationPreferenceType.REMOTE, priority=0
            )
        )
        db_session.flush()
        db_session.refresh(candidate)

        job = _make_job(
            db_session,
            role_category=RoleCategory.SWE_BACKEND,
            employment_type=EmploymentType.INTERNSHIP,
            remote_type=RemoteType.REMOTE,
            locations=["Remote - US"],
        )

        score, reasons = compute_match_score(job, candidate.preferences)

        assert score == sum(r["contribution"] for r in reasons)
        assert score == 100
