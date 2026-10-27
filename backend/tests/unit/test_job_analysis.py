from app.models.enums import DegreeLevel, FactType, FactVerificationStatus, TriState, WorkAuthStatus
from app.services.job_analysis import analyze_job_description, employer_context, match_qualifications


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
    requires_sponsorship = TriState.NO
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

STRIPE_JD = """
About Stripe Stripe is a financial infrastructure platform for businesses. Millions of companies from startups to Fortune 500s use Stripe to accept payments and grow revenue. Our internal stack includes Python, React, and Ruby used to process payments. We believe that enabling more fairness in finance is a problem rooted in code.
What you’ll do Work with senior engineers to design and implement backend services. Write tests and review code.
Minimum requirements Currently pursuing a BA/BS in Computer Science or a related field. Available for a 12-week internship in summer 2027. Experience with at least one of Python, Java, or JavaScript.
Preferred qualifications Coursework or internships involving distributed systems. Familiarity with Go.
Benefits Inclusive healthcare coverage, paid time off, and employee resource groups.
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
    assert any("redis" in item["text"].lower() for item in report["uncertain"])
    assert not any("redis" in item["text"].lower() for item in report["missing"])


def test_matching_never_infers_work_auth_from_unverified_profile():
    candidate = _Candidate()
    candidate.work_authorization_status = WorkAuthStatus.UNKNOWN
    report = match_qualifications(analyze_job_description(JD), [], candidate)
    assert report["matched"] == []
    assert any(item["group"] == "work_authorization" for item in report["uncertain"])
    assert not any(item["group"] == "work_authorization" for item in report["missing"])


def test_stripe_listing_does_not_treat_company_marketing_as_qualifications():
    analysis = analyze_job_description(STRIPE_JD)
    required = " ".join(item["text"] for item in analysis["required"]).lower()
    company = " ".join(item["text"] for item in analysis["company"]).lower()
    preferred = " ".join(item["text"] for item in analysis["preferred"]).lower()
    assert "financial infrastructure" in company
    assert "fortune 500" in company
    assert "healthcare" in " ".join(item["text"] for item in analysis["benefits"]).lower()
    assert analysis["required"], "Stripe minimum requirements must be extracted"
    assert "computer science" in required or "ba/bs" in required
    assert "python" in required
    assert "go" in preferred
    assert "financial infrastructure" not in required
    assert "fortune 500" not in required
    techs = {item["text"] for item in analysis["technologies"]}
    assert "python" in techs
    assert "react" not in techs
    assert "ruby" not in techs

    facts = [_Fact(FactType.SKILL, "Languages", {"items": ["Python"]})]
    report = match_qualifications(analysis, facts, _Candidate())
    matched = " ".join(item["text"] for item in report["matched"]).lower()
    missing = " ".join(item["text"] for item in report["missing"]).lower()
    uncertain = " ".join(item["text"] for item in report["uncertain"]).lower()
    assert "python" in matched
    assert "financial infrastructure" not in matched
    assert "fortune 500" not in matched
    assert "go" in uncertain
    assert "go" not in missing


def test_unknown_skill_is_not_confirmed_missing():
    analysis = {
        "required": [{"text": "Experience with Rust", "evidence": "stated"}],
        "preferred": [],
        "technologies": [{"text": "rust", "evidence": "stated"}],
        "education": [],
        "experience": [],
        "work_authorization": [],
    }
    report = match_qualifications(analysis, [_Fact(FactType.SKILL, "Languages", {"items": ["Python"]})], _Candidate())
    assert report["missing"] == []
    assert any("rust" in item["text"].lower() for item in report["uncertain"])


def test_confirmed_missing_requires_contradiction():
    candidate = _Candidate()
    candidate.requires_sponsorship = TriState.YES
    analysis = {
        "required": [],
        "preferred": [],
        "technologies": [],
        "education": [],
        "experience": [],
        "work_authorization": [{"text": "We are unable to sponsor visas for this role.", "evidence": "stated"}],
    }
    report = match_qualifications(analysis, [], candidate)
    assert any("sponsor" in item["text"].lower() for item in report["missing"])


def test_employer_context_excludes_benefits_and_requirements():
    analysis = analyze_job_description(STRIPE_JD)
    context = employer_context(analysis, "Stripe", "Software Engineer Intern").lower()
    assert "stripe" in context
    assert "backend services" in context
    assert "healthcare" not in context
