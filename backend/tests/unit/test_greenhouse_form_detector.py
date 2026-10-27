from app.api.autofill import detect_application_form, router
from app.autofill.greenhouse import detect_application
from app.autofill.materials import Materials, select_resume
from app.autofill.urls import classify_apply_url, greenhouse_application_url, same_greenhouse_application
from app.schemas.autofill import AutofillDetectRequest

STANDARD = """
<html><body>
  <form id="application" method="post" action="/apply">
    <label for="first_name">First Name *</label>
    <input id="first_name" name="job_application[first_name]" type="text" required>
    <label for="last_name">Last Name *</label>
    <input id="last_name" name="job_application[last_name]" autocomplete="family-name" required>
    <label for="email">Email</label>
    <input id="email" name="job_application[email]" type="email" required>
    <label for="phone">Phone</label>
    <input id="phone" name="job_application[phone]" type="tel">
    <label for="job_application_location">Location</label>
    <input id="job_application_location" name="job_application[location]" type="text">
    <label for="resume">Resume/CV *</label>
    <input id="resume" name="job_application[resume]" type="file" required>
    <label for="linkedin">LinkedIn Profile</label>
    <input id="linkedin" name="job_application[linkedin_profile]" type="url">
    <label for="github">GitHub URL</label>
    <input id="github" name="job_application[github]" type="url">
    <label for="website">Website</label>
    <input id="website" name="job_application[website]" type="url">
    <label for="ack">Keep me posted</label>
    <input id="ack" type="checkbox" name="job_application[follow_up]">
    <label for="hear">How did you hear about this internship?</label>
    <textarea id="hear" name="job_application[answers_attributes][0][text_value]"></textarea>
    <label for="school">School</label>
    <select id="school" name="job_application[school]">
      <option>Select</option>
      <option>Example State University</option>
    </select>
    <button type="submit">Submit application</button>
  </form>
</body></html>
"""

ALTERNATE = """
<html><body>
  <div id="application_form">
    <label>Given name<input name="candidateFirstName" type="text" required></label>
    <label>Family name<input aria-label="Family name" name="candidateLastName" type="text"></label>
    <input aria-labelledby="mail-label" name="contactEmail" type="text" required>
    <span id="mail-label">Email address *</span>
    <textarea placeholder="Phone number" name="mobile"></textarea>
    <label>Portfolio URL<input name="portfolioUrl" type="url"></label>
  </div>
</body></html>
"""

MISSING = """
<form id="application">
  <input class="first_name" type="text">
  <input id="mystery" type="text">
  <textarea name="notes"></textarea>
</form>
"""

SENSITIVE = """
<form id="application">
  <label for="work_auth">Are you authorized to work in the United States?</label>
  <select id="work_auth" name="job_application[answers_attributes][1][boolean_value]" required>
    <option>Yes</option>
    <option>No</option>
  </select>
  <fieldset>
    <legend>Gender</legend>
    <label><input type="radio" name="gender" value="f"> Female</label>
    <label><input type="radio" name="gender" value="m"> Male</label>
  </fieldset>
  <div class="g-recaptcha"></div>
</form>
"""

URL = "https://boards.greenhouse.io/acme/jobs/12345"


def _by_semantic(detection):
    return {field.semantic: field for field in detection.fields}


def test_greenhouse_job_urls_are_allow_listed_and_lookalikes_are_rejected():
    job = classify_apply_url("https://job-boards.greenhouse.io/northwind/jobs/99?gh_src=abc")
    assert job.supported is True
    assert job.board_token == "northwind"
    assert job.job_id == "99"
    embed = classify_apply_url("https://boards.eu.greenhouse.io/embed/job_app?for=acme&token=42")
    assert embed.supported is True
    assert embed.job_id == "42"
    assert classify_apply_url("https://boards.greenhouse.io.evil.com/acme/jobs/1").supported is False
    assert classify_apply_url("https://user:pass@boards.greenhouse.io/acme/jobs/1").supported is False
    assert classify_apply_url("http://boards.greenhouse.io/acme/jobs/1").supported is False
    assert classify_apply_url("javascript:alert(1)").supported is False
    lever = classify_apply_url("https://jobs.lever.co/acme/abc")
    assert lever.supported is False
    assert lever.provider == "lever"
    ashby = classify_apply_url("https://jobs.ashbyhq.com/acme/job-1")
    assert ashby.provider == "ashby"
    assert classify_apply_url("https://boards.greenhouse.io/acme").reason


def test_company_career_page_resolves_to_the_greenhouse_form():
    url, note = greenhouse_application_url(
        "https://stripe.com/jobs/search?gh_jid=8128744",
        provider="greenhouse",
        board_token="stripe",
        external_id="8128744",
    )
    assert note == ""
    assert url == "https://boards.greenhouse.io/embed/job_app?for=stripe&token=8128744"
    direct, _ = greenhouse_application_url(
        "https://boards.greenhouse.io/acme/jobs/15",
        provider="greenhouse",
        board_token="acme",
        external_id="15",
    )
    assert direct == "https://boards.greenhouse.io/acme/jobs/15"
    missing, reason = greenhouse_application_url(
        "https://example.com/jobs/1",
        provider="greenhouse",
        board_token="",
        external_id="1",
    )
    assert missing is None
    assert "board token" in reason
    lever_url, lever_note = greenhouse_application_url(
        "https://jobs.lever.co/acme/abc",
        provider="lever",
        board_token="acme",
        external_id="abc",
    )
    assert lever_url is None
    assert lever_note == ""


def test_standard_greenhouse_form_maps_labels_and_leaves_questions_unknown():
    detection = detect_application(URL, STANDARD)
    fields = _by_semantic(detection)
    assert detection.supported is True
    assert detection.form_found is True
    assert detection.job_id == "12345"
    assert fields["first_name"].required is True
    assert fields["first_name"].input_type == "text"
    assert fields["last_name"].semantic == "last_name"
    assert fields["email"].input_type == "email"
    assert fields["phone"].required is False
    assert fields["location"].label == "Location"
    assert fields["resume"].input_type == "file"
    assert fields["linkedin"].input_type == "url"
    assert fields["github"].label == "GitHub URL"
    assert fields["portfolio"].label == "Website"
    assert fields["custom_question"].label.startswith("How did you hear")
    school = next(field for field in detection.fields if field.element_id == "school")
    assert school.semantic == "school"
    assert school.input_type == "select"
    assert "Example State University" in school.options
    follow_up = next(field for field in detection.fields if field.element_id == "ack")
    assert follow_up.input_type == "checkbox"
    assert follow_up.semantic == "unknown"
    assert any("submit" in warning.casefold() for warning in detection.warnings)
    assert all(field.semantic != "submit" for field in detection.fields)


def test_alternate_layout_uses_accessible_names_not_css_classes():
    detection = detect_application("https://job-boards.greenhouse.io/acme/jobs/7", ALTERNATE)
    fields = _by_semantic(detection)
    assert detection.form_found is False
    assert fields["first_name"].label == "Given name"
    assert fields["last_name"].confidence == "high"
    assert fields["email"].required is True
    assert fields["phone"].confidence == "low"
    assert fields["portfolio"].name == "portfolioUrl"


def test_missing_labels_are_not_guessed_from_class_names():
    detection = detect_application(URL, MISSING)
    assert detection.fields
    assert {field.semantic for field in detection.fields} == {"unknown"}
    assert all(field.confidence == "low" for field in detection.fields)


def test_sensitive_questions_and_captcha_are_flagged_without_being_filled():
    detection = detect_application(URL, SENSITIVE)
    sensitive = [field for field in detection.fields if field.semantic == "sensitive"]
    assert len(sensitive) == 2
    assert any(field.required is True for field in sensitive)
    gender = next(field for field in sensitive if "Gender" in field.label)
    assert gender.input_type == "radio"
    assert "Female" in gender.options
    assert detection.blockers == ["captcha"]
    assert detection.supported is True


GREENHOUSE_LIKE = """
<html><body>
  <script>
    var config = {"GOOGLE_RECAPTCHA_INVISIBLE_KEY":"test-key","GOOGLE_RECAPTCHA_ENDPOINT":"https://www.recaptcha.net/recaptcha/enterprise.js"};
  </script>
  <form id="application">
    <label for="first_name">First Name *</label>
    <input id="first_name" name="job_application[first_name]" type="text" required>
    <label for="phone">Phone</label>
    <div>
      <label for="phone_country">Country</label>
      <select id="phone_country" name="job_application[phone_country]"><option>United States</option></select>
      <input id="phone" name="job_application[phone]" type="tel">
    </div>
    <label for="city">City</label>
    <input id="city" name="job_application[city]" type="text">
    <label for="resume">Resume/CV *</label>
    <input id="resume" name="job_application[resume]" type="file" accept=".pdf" style="display:none">
    <div style="display:none">
      <label for="resume_template">Resume/CV *</label>
      <input id="resume_template" name="job_application[resume_template]" type="file">
    </div>
    <label for="school">School</label>
    <select id="school" name="job_application[educations][][school_name_id]"><option>Example University</option></select>
    <div role="combobox" aria-label="School"></div>
    <input class="select2-search__field" type="search" role="searchbox" tabindex="-1">
    <label for="degree">Degree</label>
    <select id="degree" name="job_application[educations][][degree_id]"><option>Bachelor's</option></select>
    <label for="discipline">Discipline</label>
    <select id="discipline" name="job_application[educations][][discipline_id]"><option>Computer Science</option></select>
    <label for="school_2">School</label>
    <select id="school_2" name="job_application[educations][][school_name_id_2]"><option>Other University</option></select>
  </form>
</body></html>
"""


def test_invisible_recaptcha_configuration_is_not_an_active_challenge():
    detection = detect_application(URL, GREENHOUSE_LIKE)
    assert detection.blockers == []
    hidden = detect_application(URL, '<form id="application"><div class="g-recaptcha" data-size="invisible"></div></form>')
    assert hidden.blockers == []
    script_only = detect_application(URL, '<form id="application"><script src="https://www.recaptcha.net/recaptcha/enterprise.js"></script></form>')
    assert script_only.blockers == []
    solved = detect_application(
        URL,
        '<form id="application"><div class="g-recaptcha"></div><textarea name="g-recaptcha-response">completed-token</textarea></form>',
    )
    assert solved.blockers == []
    active = detect_application(URL, '<form id="application"><iframe title="recaptcha challenge" src="https://www.recaptcha.net/recaptcha/enterprise/bframe"></iframe></form>')
    assert active.blockers == ["captcha"]


def test_greenhouse_custom_controls_are_recognized_once():
    detection = detect_application(URL, GREENHOUSE_LIKE)
    fields = _by_semantic(detection)
    assert fields["phone"].input_type == "tel"
    assert fields["phone_country"].label == "Country"
    assert fields["location"].element_id == "city"
    assert fields["resume"].input_type == "file"
    assert fields["resume"].required is True
    assert fields["school"].label == "School"
    assert fields["degree"].label == "Degree"
    assert fields["discipline"].label == "Discipline"
    assert [field.element_id for field in detection.fields if field.semantic == "school"] == ["school", "school_2"]
    assert all(field.semantic != "unknown" or field.label != "Country" for field in detection.fields)
    assert not any(field.element_id == "resume_template" for field in detection.fields)
    assert sum(1 for field in detection.fields if _normalize(field.label) == "school" and not field.name) == 0


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("/", " ").split())


def test_two_stripe_preparations_do_not_share_a_resume():
    first, first_note = greenhouse_application_url(
        "https://stripe.com/jobs/search?gh_jid=8128744",
        provider="greenhouse",
        board_token="stripe",
        external_id="8128744",
    )
    second, second_note = greenhouse_application_url(
        "https://stripe.com/jobs/search?gh_jid=8128745",
        provider="greenhouse",
        board_token="stripe",
        external_id="8128745",
    )
    assert first_note == "" and second_note == ""
    assert first is not None and second is not None
    same, same_problem = same_greenhouse_application(first, first)
    other, other_problem = same_greenhouse_application(first, second)
    assert same is True and same_problem == ""
    assert other is False
    assert "stripe/8128744" in other_problem
    assert "stripe/8128745" in other_problem
    assert "not the same application" in other_problem
    refused = select_resume(Materials(preparation_id=2, link_problem=other_problem), ".pdf", True, "resume")
    assert refused.eligible_for_attach is False
    assert refused.display_name == ""
    assert refused.preparation_id == 2


def test_empty_malformed_and_verification_pages_stop_safely():
    empty = detect_application(URL, "")
    assert empty.supported is True
    assert empty.form_found is False
    assert empty.fields == []
    broken = detect_application(URL, "<form id='application'><label>Email<input name='email'")
    assert broken.supported is True
    assert isinstance(broken.fields, list)
    named = detect_application(URL, "<form id='application'><input name='email'></form>")
    assert _by_semantic(named)["email"].input_type == "text"
    challenge = detect_application(URL, "<form id='application'><p>Enter the verification code from your authenticator.</p></form>")
    assert challenge.blockers == ["mfa"]
    assert challenge.fields == []


def test_detect_route_returns_fields_and_one_confirmed_submit_path():
    result = detect_application_form(AutofillDetectRequest(url=URL, html=STANDARD))
    assert result.supported is True
    assert any(field.semantic == "resume" and field.input_type == "file" for field in result.fields)
    paths = {route.path for route in router.routes}
    assert paths == {
        "/api/autofill/detect",
        "/api/autofill/plan",
        "/api/autofill/sessions",
        "/api/autofill/sessions/{session_id}",
        "/api/autofill/sessions/{session_id}/fill",
        "/api/autofill/sessions/{session_id}/submit",
        "/api/autofill/sessions/{session_id}/cancel",
    }
    assert sum("submit" in route.path for route in router.routes) == 1


def test_unsupported_url_does_not_return_fillable_fields():
    detection = detect_application("https://jobs.lever.co/acme/role", STANDARD)
    assert detection.supported is False
    assert detection.fields == []
    assert detection.rejection_reason
