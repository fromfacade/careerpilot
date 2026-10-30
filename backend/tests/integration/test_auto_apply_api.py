"""Auto-Apply settings persist on the candidate and never submit an application."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.application import TrackedApplication
from app.models.enums import ApplicationStatus, JobProvider, ResumeFileFormat
from app.models.job import Job
from app.models.job_source import Employer, JobSource
from app.models.resume import Resume
from app.services.auto_apply import usage_counts

EXPLANATION = (
    "Auto-Apply allows CareerPilot to submit eligible, complete "
    "applications automatically within your configured limits."
)


def _candidate(client):
    created = client.post(
        "/api/candidate",
        json={"full_name": "Ada Lovelace", "email": "ada.auto-apply@example.com"},
    )
    assert created.status_code == 201, created.text
    return created.json()


def _grant(**overrides):
    body = {
        "enabled": True,
        "acknowledge": True,
        "provider": "greenhouse",
        "job_categories": ["swe_backend"],
        "employment_types": ["internship"],
        "locations": [" Santa Cruz, CA ", "santa cruz, ca"],
        "min_match_score": 70,
        "max_per_day": 3,
        "max_per_session": 1,
        "resume_ids": [],
        "expires_at": "2027-01-15T18:00:00Z",
    }
    body.update(overrides)
    return body


def _resume(db_session, candidate_id, *, approved):
    row = Resume(
        candidate_id=candidate_id,
        original_filename="fictional.pdf",
        file_format=ResumeFileFormat.PDF,
        storage_path=f"resumes/fictional-{candidate_id}-{approved}.pdf",
        file_size_bytes=128,
        sha256_checksum=f"checksum-{candidate_id}-{approved}",
        profile_name="Fictional backend profile",
        is_approved=approved,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _job(db_session):
    employer = Employer(name="Fictional Labs")
    db_session.add(employer)
    db_session.flush()
    source = JobSource(employer_id=employer.id, provider=JobProvider.GREENHOUSE, board_token="fictional-labs")
    db_session.add(source)
    db_session.flush()
    job = Job(
        job_source_id=source.id,
        external_id="fictional-intern",
        title="Backend Intern",
        description_text="Build fictional services.",
        apply_url="https://boards.greenhouse.io/fictionallabs/jobs/1",
        canonical_url="https://example.test/jobs/fictional-intern",
        content_hash="hash-fictional-intern",
        dedupe_key="fictional-labs|fictional-intern",
        raw_payload={"id": "fictional-intern"},
    )
    db_session.add(job)
    db_session.flush()
    return job


def test_auto_apply_is_review_mode_until_the_user_opts_in(client):
    assert client.get("/api/candidate/auto-apply").status_code == 404
    _candidate(client)
    body = client.get("/api/candidate/auto-apply").json()
    assert body["enabled"] is False
    assert body["acknowledged"] is False
    assert body["active"] is False
    assert body["mode"] == "review"
    assert body["provider"] == "greenhouse"
    assert body["automatic_submission"] is False
    assert body["explanation"] == EXPLANATION

    refused = client.put("/api/candidate/auto-apply", json=_grant(acknowledge=False))
    assert refused.status_code == 422
    assert "acknowledgement" in refused.json()["detail"]
    assert client.get("/api/candidate/auto-apply").json()["enabled"] is False


def test_authorization_persists_and_can_be_revoked(client):
    _candidate(client)
    saved = client.put("/api/candidate/auto-apply", json=_grant())
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["active"] is True
    assert body["mode"] == "auto_apply"
    assert body["job_categories"] == ["swe_backend"]
    assert body["employment_types"] == ["internship"]
    assert body["locations"] == ["Santa Cruz, CA"]
    assert body["min_match_score"] == 70
    assert body["max_per_day"] == 3
    assert body["max_per_session"] == 1
    assert body["automatic_submission"] is False
    again = client.get("/api/candidate/auto-apply")
    assert again.json()["expires_at"].startswith("2027-01-15")

    revoked = client.put("/api/candidate/auto-apply", json=_grant(enabled=False, acknowledge=False))
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["enabled"] is False
    assert revoked.json()["active"] is False
    assert revoked.json()["mode"] == "review"
    assert client.get("/api/candidate/auto-apply").json()["active"] is False


def test_expired_authorization_is_inactive(client, monkeypatch):
    _candidate(client)
    saved = client.put("/api/candidate/auto-apply", json=_grant())
    assert saved.status_code == 200, saved.text
    monkeypatch.setattr(
        "app.services.auto_apply.now_utc",
        lambda: datetime(2027, 2, 1, tzinfo=timezone.utc),
    )
    body = client.get("/api/candidate/auto-apply").json()
    assert body["enabled"] is True
    assert body["active"] is False
    assert body["mode"] == "review"
    assert body["inactive_reason"] == "The authorization has expired."


def test_unapproved_resume_and_other_boards_are_rejected(client, db_session):
    candidate = _candidate(client)
    resume = _resume(db_session, candidate["id"], approved=False)
    refused = client.put("/api/candidate/auto-apply", json=_grant(resume_ids=[resume.id]))
    assert refused.status_code == 422
    other_board = client.put("/api/candidate/auto-apply", json=_grant(provider="lever"))
    assert other_board.status_code == 422
    approved = _resume(db_session, candidate["id"], approved=True)
    saved = client.put("/api/candidate/auto-apply", json=_grant(resume_ids=[approved.id]))
    assert saved.status_code == 200, saved.text
    assert saved.json()["resumes"] == [
        {"id": approved.id, "profile_name": "Fictional backend profile", "is_approved": True}
    ]


def test_limits_use_the_existing_tracked_applications(client, db_session):
    candidate = _candidate(client)
    job = _job(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        TrackedApplication(
            candidate_id=candidate["id"],
            job_id=job.id,
            employer="Fictional Labs",
            status=ApplicationStatus.SUBMITTED,
            submitted_at=now,
        )
    )
    db_session.flush()
    counts = usage_counts(db_session, candidate["id"], now - timedelta(hours=1), now)
    assert counts.submitted_today == 1
    assert counts.submitted_this_session == 1


def test_saving_authorization_does_not_submit(client, db_session):
    candidate = _candidate(client)
    job = _job(db_session)
    tracked = TrackedApplication(
        candidate_id=candidate["id"],
        job_id=job.id,
        employer="Fictional Labs",
        status=ApplicationStatus.READY_TO_SUBMIT,
    )
    db_session.add(tracked)
    db_session.flush()
    saved = client.put("/api/candidate/auto-apply", json=_grant())
    assert saved.status_code == 200, saved.text
    assert saved.json()["automatic_submission"] is False
    missing = client.post("/api/candidate/auto-apply/submit", json={})
    assert missing.status_code == 404
    db_session.expire_all()
    stored = db_session.get(TrackedApplication, tracked.id)
    assert stored.status == ApplicationStatus.READY_TO_SUBMIT
    assert stored.submitted_at is None
