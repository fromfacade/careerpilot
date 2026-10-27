from app.models.enums import DegreeLevel, FactType, FactVerificationStatus, WorkAuthStatus
from app.services.job_analysis import analyze_job_description, match_qualifications


class _Fact:
    def __init__(self, fact_type, fact_key, fact_value):
        self.fact_type = fact_type
        self.fact_key = fact_key
        self.fact_value = fact_value
        self.verification_status = FactVerificationStatus.VERIFIED


class _Candidate:
    school = "UC Santa Cruz"
    degree_level = DegreeLevel.BACHELORS
    major = "Computer Science"
    work_authorization_status = WorkAuthStatus.US_CITIZEN
    requires_sponsorship = None
    current_location = "California"


JD = """
Requirements:
- Experience with Python and FastAPI
- Authorized to work in the United States

Preferred:
- Redis

Responsibilities:
- Build backend services
"""


def test_analysis_separates_stated_requirements_and_tech():
    analysis = analyze_job_description(JD)
    required = " ".join(item["text"] for item in analysis["required"]).lower()
    assert "python" in required
    assert any(item["text"] == "python" and item["evidence"] == "stated" for item in analysis["technologies"])
    assert any(item["evidence"] == "stated" for item in analysis["work_authorization"])
    assert any("redis" in item["text"] for item in analysis["preferred"] + analysis["technologies"])


def test_matching_requires_verified_evidence():
    facts = [_Fact(FactType.SKILL, "Languages", {"items": ["Python", "FastAPI"]})]
    report = match_qualifications(analyze_job_description(JD), facts, _Candidate())
    matched_text = " ".join(item["text"] for item in report["matched"]).lower()
    assert "python" in matched_text
    assert "fastapi" in matched_text
    assert any(item["group"] == "work_authorization" for item in report["matched"])
    assert any("redis" in item["text"].lower() for item in report["missing"] + report["uncertain"])


def test_matching_never_infers_work_auth_from_unverified_profile():
    candidate = _Candidate()
    candidate.work_authorization_status = WorkAuthStatus.UNKNOWN
    report = match_qualifications(analyze_job_description(JD), [], candidate)
    assert report["matched"] == []
    assert any(item["group"] == "work_authorization" for item in report["missing"])
