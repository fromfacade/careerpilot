from __future__ import annotations

from app.models.enums import EmploymentType, RemoteType, RoleCategory, SeniorityLevel
from app.sources import normalize


class TestHtmlToText:
    def test_strips_tags(self):
        assert normalize.html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_handles_double_encoded_entities(self):
        # Observed in real Greenhouse responses.
        raw = "&lt;h2&gt;&lt;strong&gt;Who we are&lt;/strong&gt;&lt;/h2&gt;"
        assert normalize.html_to_text(raw) == "Who we are"

    def test_handles_none_and_empty(self):
        assert normalize.html_to_text(None) == ""
        assert normalize.html_to_text("") == ""

    def test_preserves_block_breaks(self):
        assert normalize.html_to_text("<p>a</p>\n\n<p>b</p>") == "a\n\nb"

    def test_keeps_greenhouse_headings_on_their_own_lines(self):
        raw = (
            "&lt;h2&gt;About Stripe&lt;/h2&gt;&lt;p&gt;Stripe is a financial "
            "infrastructure platform.&lt;/p&gt;&lt;h2&gt;Minimum requirements&lt;/h2&gt;"
            "&lt;ul&gt;&lt;li&gt;Experience with Python&lt;/li&gt;&lt;/ul&gt;"
        )
        text = normalize.html_to_text(raw)
        assert "About Stripe\n" in text or text.startswith("About Stripe")
        assert "Minimum requirements" in text
        assert text.index("About Stripe") < text.index("Minimum requirements")
        assert text.index("Minimum requirements") < text.index("Experience with Python")


class TestNormalizeUrl:
    def test_lowercases_scheme_and_host(self):
        assert normalize.normalize_url("HTTPS://Example.COM/jobs/1") == "https://example.com/jobs/1"

    def test_strips_trailing_slash(self):
        assert normalize.normalize_url("https://example.com/jobs/1/") == "https://example.com/jobs/1"

    def test_strips_tracking_params(self):
        assert (
            normalize.normalize_url("https://example.com/jobs/1?utm_source=x&gh_jid=123&real=keep")
            == "https://example.com/jobs/1?real=keep"
        )

    def test_strips_default_ports(self):
        assert normalize.normalize_url("https://example.com:443/jobs/1") == "https://example.com/jobs/1"


class TestContentHash:
    def test_same_input_same_hash(self):
        h1 = normalize.compute_content_hash("Title", "desc", ["SF", "NY"])
        h2 = normalize.compute_content_hash("Title", "desc", ["NY", "SF"])  # order shouldn't matter
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = normalize.compute_content_hash("Title A", "desc", ["SF"])
        h2 = normalize.compute_content_hash("Title B", "desc", ["SF"])
        assert h1 != h2

    def test_case_insensitive(self):
        h1 = normalize.compute_content_hash("Title", "Desc", ["SF"])
        h2 = normalize.compute_content_hash("title", "desc", ["sf"])
        assert h1 == h2


class TestDedupeKey:
    def test_same_employer_title_location_same_key(self):
        k1 = normalize.compute_dedupe_key("Acme", "Software Engineer", "San Francisco, CA")
        k2 = normalize.compute_dedupe_key("acme", "software engineer", "san francisco, ca")
        assert k1 == k2

    def test_different_employer_different_key(self):
        k1 = normalize.compute_dedupe_key("Acme", "Software Engineer", "San Francisco, CA")
        k2 = normalize.compute_dedupe_key("Globex", "Software Engineer", "San Francisco, CA")
        assert k1 != k2


class TestInferEmploymentType:
    def test_internship_from_title(self):
        assert normalize.infer_employment_type("Software Engineering Intern", None) == EmploymentType.INTERNSHIP

    def test_new_grad_from_title(self):
        assert normalize.infer_employment_type("New Grad Software Engineer", None) == EmploymentType.NEW_GRAD

    def test_contract_from_title(self):
        assert normalize.infer_employment_type("Contract Backend Engineer", None) == EmploymentType.CONTRACT

    def test_full_time_from_hint(self):
        assert normalize.infer_employment_type("Software Engineer", "FullTime") == EmploymentType.FULL_TIME

    def test_unknown_when_no_signal(self):
        assert normalize.infer_employment_type("Software Engineer", None) == EmploymentType.UNKNOWN


class TestInferRoleCategory:
    def test_backend(self):
        assert normalize.infer_role_category("Backend Software Engineer") == RoleCategory.SWE_BACKEND

    def test_frontend(self):
        assert normalize.infer_role_category("Frontend Engineer") == RoleCategory.SWE_FRONTEND

    def test_fullstack(self):
        assert normalize.infer_role_category("Full Stack Developer") == RoleCategory.SWE_FULLSTACK

    def test_infrastructure(self):
        assert normalize.infer_role_category("Site Reliability Engineer") == RoleCategory.INFRASTRUCTURE

    def test_ai_engineering(self):
        assert normalize.infer_role_category("Machine Learning Engineer") == RoleCategory.AI_ENGINEERING

    def test_cybersecurity(self):
        assert normalize.infer_role_category("Security Engineer") == RoleCategory.CYBERSECURITY

    def test_qa(self):
        assert normalize.infer_role_category("QA Engineer") == RoleCategory.QA

    def test_it_support(self):
        assert normalize.infer_role_category("IT Support Specialist") == RoleCategory.IT_SUPPORT

    def test_generic_software_engineer_defaults_to_backend(self):
        assert normalize.infer_role_category("Software Engineer") == RoleCategory.SWE_BACKEND

    def test_other_when_no_match(self):
        assert normalize.infer_role_category("Marketing Manager") == RoleCategory.OTHER


class TestInferRemoteType:
    def test_from_hint(self):
        assert normalize.infer_remote_type(["San Francisco"], "Remote") == RemoteType.REMOTE
        assert normalize.infer_remote_type(["San Francisco"], "Hybrid") == RemoteType.HYBRID
        assert normalize.infer_remote_type(["San Francisco"], "Onsite") == RemoteType.ONSITE

    def test_from_location_text(self):
        assert normalize.infer_remote_type(["Remote - US"], None) == RemoteType.REMOTE

    def test_unknown_when_no_signal(self):
        assert normalize.infer_remote_type(["San Francisco, CA"], None) == RemoteType.UNKNOWN


class TestInferSeniorityLevel:
    def test_entry_level_titles_are_unknown_not_assumed_entry(self):
        # We never guess ENTRY from a title alone -- only an explicit
        # senior+ keyword produces a non-UNKNOWN result.
        assert normalize.infer_seniority_level("Software Engineering Intern") == SeniorityLevel.UNKNOWN
        assert normalize.infer_seniority_level("Software Engineer I") == SeniorityLevel.UNKNOWN

    def test_senior(self):
        assert normalize.infer_seniority_level("Senior Software Engineer") == SeniorityLevel.SENIOR
        assert normalize.infer_seniority_level("Sr. Backend Engineer") == SeniorityLevel.SENIOR

    def test_staff_or_principal(self):
        assert normalize.infer_seniority_level("Staff Software Engineer") == SeniorityLevel.STAFF_OR_PRINCIPAL
        assert normalize.infer_seniority_level("Principal Engineer") == SeniorityLevel.STAFF_OR_PRINCIPAL

    def test_manager_or_director(self):
        assert normalize.infer_seniority_level("Director of Engineering") == SeniorityLevel.MANAGER_OR_DIRECTOR
        assert normalize.infer_seniority_level("Engineering Manager") == SeniorityLevel.MANAGER_OR_DIRECTOR
        assert normalize.infer_seniority_level("Head of Platform") == SeniorityLevel.MANAGER_OR_DIRECTOR

    def test_executive(self):
        assert normalize.infer_seniority_level("Chief Technology Officer") == SeniorityLevel.EXECUTIVE
        assert normalize.infer_seniority_level("VP of Engineering") == SeniorityLevel.EXECUTIVE

    def test_most_senior_signal_wins_on_conflicting_keywords(self):
        assert normalize.infer_seniority_level("Senior Director of Engineering") == SeniorityLevel.MANAGER_OR_DIRECTOR

    def test_account_and_office_manager_are_not_flagged_as_management(self):
        # These are the exact real-world titles that motivated this guard --
        # "Account Manager" / "Office Manager" are not people-leadership
        # seniority signals, and we'd rather say UNKNOWN than mislabel them.
        assert normalize.infer_seniority_level("Strategic Account Manager") == SeniorityLevel.UNKNOWN
        assert normalize.infer_seniority_level("Office Manager") == SeniorityLevel.UNKNOWN


class TestInferIsNonTechnical:
    def test_administrative_business_partner_is_non_technical(self):
        # The exact real-world example that motivated this: a job titled
        # "Administrative Business Partner" must never be treated as a
        # relevant match for a technical job search.
        assert normalize.infer_is_non_technical("Administrative Business Partner") is True

    def test_recruiting_sales_and_hr_titles_are_non_technical(self):
        assert normalize.infer_is_non_technical("Technical Recruiter") is True
        assert normalize.infer_is_non_technical("Account Executive") is True
        assert normalize.infer_is_non_technical("HR Business Partner") is True

    def test_software_engineer_is_not_flagged(self):
        assert normalize.infer_is_non_technical("Senior Software Engineer") is False

    def test_product_manager_and_designer_are_not_flagged(self):
        # Deliberately ambiguous roles are left alone here (see comment in
        # normalize.py) rather than risk a false "not relevant" verdict --
        # they fall through to an UNKNOWN relevance signal instead.
        assert normalize.infer_is_non_technical("Product Manager") is False
        assert normalize.infer_is_non_technical("Product Designer") is False
