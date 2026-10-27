from app.api.autofill import detect_application_form, router
from app.autofill.greenhouse import detect_application
from app.autofill.urls import classify_apply_url, greenhouse_application_url
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
    assert school.semantic == "unknown"
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


def test_detect_route_returns_fields_and_exposes_no_submit_path():
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
        "/api/autofill/sessions/{session_id}/cancel",
    }
    assert all("submit" not in route.path for route in router.routes)


def test_unsupported_url_does_not_return_fillable_fields():
    detection = detect_application("https://jobs.lever.co/acme/role", STANDARD)
    assert detection.supported is False
    assert detection.fields == []
    assert detection.rejection_reason
