from __future__ import annotations

from app.models.enums import EmploymentType, RemoteType, RoleCategory
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

    def test_collapses_whitespace(self):
        assert normalize.html_to_text("<p>a</p>\n\n<p>b</p>") == "a b"


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
