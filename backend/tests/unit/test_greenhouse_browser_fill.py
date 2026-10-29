import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from app.api.autofill import require_browser_token
from app.autofill.actions import SubmissionBlocked, decide_fill, refuse_submission, resume_marker, reviewed_fields
from app.autofill.browser_fill import apply_actions, install_navigation_guard, open_application, NavigationBlocked
from app.autofill.actions import FillAction
from app.autofill.mapping import FactView, ProfileView, plan_autofill
from app.autofill.materials import Materials, ResumeFileView, TailoredFileView
from app.autofill.urls import navigation_allowed
from app.core.local_auth import load_or_create_token

URL = "https://boards.greenhouse.io/acme/jobs/12345"
PROFILE = ProfileView(candidate_id=7, full_name="Ada Lovelace", email="ada@example.com", phone="555-0100")

FORM = """
<form id="application" onsubmit="window.__submitted = true; return false;">
  <label for="first_name">First Name *</label>
  <input id="first_name" name="job_application[first_name]" required>
  <label for="email">Email *</label>
  <input id="email" name="job_application[email]" type="email" required value="kept@example.com">
  <label for="phone">Phone</label>
  <input id="phone" name="job_application[phone]" type="tel">
  <label for="why">Why are you interested in this role?</label>
  <textarea id="why" name="why"></textarea>
  <label for="work">Are you authorized to work in the United States?</label>
  <select id="work" name="work"><option>Yes</option><option>No</option></select>
  <label for="resume">Resume</label>
  <input id="resume" name="job_application[resume]" type="file" accept=".pdf">
  <fieldset>
    <legend>Preferred contact</legend>
    <label><input type="radio" name="contact_method" value="email"> Email</label>
    <label><input type="radio" name="contact_method" value="phone"> Phone</label>
  </fieldset>
  <label for="school">School</label>
  <select id="school" name="school"><option>Example State</option><option>Other</option></select>
  <button type="submit" id="send">Submit application</button>
</form>
<script>window.__submitted = false;</script>
"""


def _materials(path):
    path.write_bytes(b"%PDF-1.4 fictional")
    return Materials(
        preparation_id=9,
        resume=ResumeFileView(4, "Backend SWE Resume", "pdf", True, False, str(path)),
        tailored=TailoredFileView(status="draft"),
        job_answers=[],
        library_answers=[],
    )


def _decision(html, path, **kwargs):
    plan = plan_autofill(URL, html, [], PROFILE, _materials(path))
    reviewed = reviewed_fields(plan)
    marker = resume_marker(plan)
    if marker is not None:
        reviewed[marker.field_id] = marker
    included = kwargs.get("included", {key for key in reviewed if key != "__resume__"})
    return plan, decide_fill(
        reviewed,
        plan,
        included=included,
        overwrite=kwargs.get("overwrite", set()),
        attach_resume=kwargs.get("attach_resume", True),
    )


def test_navigation_stays_on_greenhouse_hosts():
    assert navigation_allowed("https://boards.greenhouse.io/acme/jobs/1") is True
    assert navigation_allowed("https://example.com/jobs/1") is False
    assert navigation_allowed("http://boards.greenhouse.io/acme/jobs/1") is False
    try:
        open_application(None, "https://jobs.lever.co/acme/role")  # type: ignore[arg-type]
        raised = False
    except NavigationBlocked:
        raised = True
    assert raised is True


def test_plan_fills_only_eligible_fields_and_blocks_submission(tmp_path):
    plan, decision = _decision(FORM, tmp_path / "resume.pdf")
    assert decision.stop_reason is None
    assert {action.field_id for action in decision.actions} == {
        "job_application[first_name]",
        "job_application[phone]",
    }
    assert "job_application[email]" in decision.preserved
    assert decision.resume_field_id == "job_application[resume]"
    assert all(action.input_type != "submit" for action in decision.actions)
    try:
        refuse_submission("submit")
        raised = False
    except SubmissionBlocked:
        raised = True
    assert raised is True
    captcha = FORM.replace("</form>", '<div class="g-recaptcha"></div></form>')
    _captcha_plan, blocked = _decision(captcha, tmp_path / "other.pdf")
    assert blocked.stop_reason
    assert blocked.actions == []
    changed = FORM.replace('for="first_name">First Name', 'for="first_name">Given name')
    reviewed = reviewed_fields(plan)
    live = plan_autofill(URL, changed, [], PROFILE, _materials(tmp_path / "third.pdf"))
    stale = decide_fill(reviewed, live, included={"job_application[first_name]"}, overwrite=set(), attach_resume=False)
    assert "job_application[first_name]" in stale.stale


def test_browser_fills_verifies_and_does_not_submit(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fictional")
    action = FillAction(
        field_id="job_application[first_name]",
        input_type="text",
        name="job_application[first_name]",
        element_id="first_name",
        label="First Name",
        value="Ada",
        kind="contact",
    )
    radio = FillAction(
        field_id="contact_method",
        input_type="radio",
        name="contact_method",
        element_id="",
        label="Preferred contact",
        value="Email",
        kind="contact",
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(FORM)
        report = apply_actions(
            page,
            [action, radio],
            resume_field_id="job_application[resume]",
            resume_path=str(resume),
            resume_name="Backend SWE Resume",
        )
        assert report.submitted is False
        assert page.evaluate("() => window.__submitted") is False
        assert page.locator("#first_name").input_value() == "Ada"
        assert page.locator('input[name="contact_method"][value="email"]').is_checked()
        assert report.resume_status == "attached"
        assert str(resume.parent) not in report.resume_detail
        page.locator("#email").fill("edited@example.com")
        again = apply_actions(page, [], resume_field_id=None, resume_path=None, resume_name="")
        assert page.locator("#email").input_value() == "edited@example.com"
        assert again.submitted is False
        missing = apply_actions(
            page,
            [],
            resume_field_id="job_application[resume]",
            resume_path=str(tmp_path / "missing.pdf"),
            resume_name="Backend SWE Resume",
        )
        assert missing.resume_status == "failed"
        cancel = threading.Event()
        cancel.set()
        stopped = apply_actions(page, [action], resume_field_id=None, resume_path=None, resume_name="", cancel=cancel)
        assert stopped.stopped == "cancelled"
        assert stopped.outcomes == []
        browser.close()


WIDER = """
<form id="application" onsubmit="window.__submitted = true; return false;">
  <label for="phone">Phone</label>
  <label for="phone_country">Country</label>
  <select id="phone_country" name="job_application[phone_country]"><option>United Kingdom +44</option></select>
  <input id="phone" name="job_application[phone]" type="tel">
  <label for="city">City</label>
  <input id="city" name="job_application[city]">
  <label for="school">School</label>
  <select id="school" name="school"><option>Example State University</option><option>Other</option></select>
  <label for="degree">Degree</label>
  <select id="degree" name="degree"><option value="">Select</option><option>Bachelor of Arts</option></select>
  <label for="start">Start date</label>
  <input id="start" name="start">
  <label for="first_name">Given name</label>
  <input id="first_name" name="job_application[first_name]">
  <label for="resume">Resume</label>
  <input id="resume" name="job_application[resume]" type="file" accept=".pdf">
  <button type="submit">Submit application</button>
</form>
<script>window.__submitted = false;</script>
"""


def test_browser_fills_contact_education_and_keeps_the_resume_filename(tmp_path):
    stored = tmp_path / "8f3c1d0a9b224e77a1c0internal-storage.pdf"
    payload = b"%PDF-1.4 fictional-bytes"
    stored.write_bytes(payload)
    education = FactView(
        id=3,
        fact_type="education",
        fact_key="Example State University",
        fact_value={"institution": "Example State University", "degree": "B.S. Computer Science", "major": "Computer Science"},
        identity_key="education|example",
        status="active",
        verification_status="verified",
    )
    profile = ProfileView(
        candidate_id=7,
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+44 20 7946 0000",
        location="Austin, TX",
    )
    materials = Materials(
        preparation_id=9,
        resume=ResumeFileView(
            4,
            "Backend SWE Resume",
            "pdf",
            True,
            False,
            str(stored),
            original_filename="Ada_Lovelace_Resume.pdf",
        ),
        tailored=TailoredFileView(status="draft"),
    )
    previous = plan_autofill(URL, FORM, [education], profile, materials)
    live = plan_autofill(URL, WIDER, [education], profile, materials)
    renamed = decide_fill(
        reviewed_fields(previous),
        live,
        included={"job_application[first_name]"},
        overwrite=set(),
        attach_resume=False,
    )
    assert "job_application[first_name]" in renamed.stale
    reviewed = reviewed_fields(live)
    marker = resume_marker(live)
    if marker is not None:
        reviewed[marker.field_id] = marker
    decision = decide_fill(
        reviewed,
        live,
        included={item.field_id for item in live.ready},
        overwrite=set(),
        attach_resume=True,
    )
    assert decision.resume_field_id == "job_application[resume]"
    assert all(action.field_id != "start" for action in decision.actions)
    assert all(action.field_id != "degree" for action in decision.actions)
    assert live.resume.upload_name == "Ada_Lovelace_Resume.pdf"
    assert "internal-storage" not in live.resume.upload_name
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(WIDER)
        report = apply_actions(
            page,
            decision.actions,
            resume_field_id=decision.resume_field_id,
            resume_path=str(stored),
            resume_name=live.resume.upload_name,
        )
        assert report.submitted is False
        assert page.evaluate("() => window.__submitted") is False
        assert page.locator("#phone").input_value() == "2079460000"
        assert page.locator("#phone_country").input_value() == "United Kingdom +44"
        assert page.locator("#city").input_value() == "Austin"
        assert page.locator("#school").input_value() == "Example State University"
        assert page.locator("#degree").input_value() == ""
        assert page.locator("#start").input_value() == ""
        uploaded = page.locator("#resume").evaluate(
            """async (el) => {
                const file = el.files[0];
                const bytes = new Uint8Array(await file.arrayBuffer());
                let hex = '';
                for (const byte of bytes) hex += byte.toString(16).padStart(2, '0');
                return {name: file.name, hex};
            }"""
        )
        assert uploaded["name"] == "Ada_Lovelace_Resume.pdf"
        assert uploaded["hex"] == payload.hex()
        assert "internal-storage" not in report.resume_detail
        assert stored.read_bytes() == payload
        browser.close()


MENU = """
<form id="application" onsubmit="window.__submitted = true; return false;">
  <label for="first_name">First Name</label>
  <input id="first_name" name="first_name">
  <label for="email">Email</label>
  <input id="email" name="email" type="email">
  <label for="country">Country</label>
  <div class="select">
    <input id="country" role="combobox" aria-controls="country-list" aria-autocomplete="list">
    <div id="country-value" class="select__single-value"></div>
  </div>
  <ul id="country-list" role="listbox" hidden>
    <li role="option">United States +1</li>
    <li role="option">Canada +1</li>
    <li role="option">United Kingdom +44</li>
  </ul>
  <button id="flag" type="button" aria-label="Change country"></button>
  <label for="phone">Phone</label>
  <input id="phone" type="tel">
  <label for="city">Location (City)</label>
  <div class="select">
    <input id="city" role="combobox" aria-controls="city-list" aria-autocomplete="list">
    <div id="city-value" class="select__single-value"></div>
  </div>
  <ul id="city-list" role="listbox" hidden></ul>
  <button type="submit">Submit application</button>
</form>
<script>
  window.__submitted = false;
  function openList(input, listId) {
    input.addEventListener('focus', () => { document.getElementById(listId).hidden = false; });
    input.addEventListener('input', () => { document.getElementById(listId).hidden = false; });
  }
  const cities = [
    {text: 'Austin, Texas, United States', when: (q) => q.includes('tx') || q.includes('texas')},
    {text: 'Austin, Minnesota, United States', when: (q) => q === 'austin' || q.includes('minnesota')},
    {text: 'Austin, Arkansas, United States', when: (q) => q === 'austin' || q.includes('arkansas')},
    {text: 'Santa Cruz, California, United States', when: (q) => q.includes(', ca') || q.includes('california')},
    {text: 'Santa Cruz, Cape Verde', when: (q) => q.includes(', ca') || q.includes('cape')},
    {text: 'Santa Cruz, Philippines', when: (q) => q === 'santa cruz'},
    {text: 'Santa Cruz, Laguna, Philippines', when: (q) => q === 'santa cruz'},
  ];
  function showCities() {
    const query = document.getElementById('city').value.trim().toLowerCase();
    const list = document.getElementById('city-list');
    list.innerHTML = '';
    cities.filter((city) => city.when(query)).forEach((city) => {
      const item = document.createElement('li');
      item.setAttribute('role', 'option');
      item.textContent = city.text;
      list.appendChild(item);
    });
    list.hidden = false;
  }
  openList(document.getElementById('country'), 'country-list');
  document.getElementById('city').addEventListener('focus', showCities);
  document.getElementById('city').addEventListener('input', showCities);
  document.getElementById('country-list').addEventListener('click', (event) => {
    const option = event.target.closest('[role=option]');
    if (!option) return;
    const name = option.textContent.trim().split('+')[0].trim();
    document.getElementById('flag').setAttribute('aria-label', 'Change country, selected ' + name + ' (+1)');
    document.getElementById('country-value').textContent = option.textContent.trim();
    document.getElementById('country-list').hidden = true;
  });
  document.getElementById('city-list').addEventListener('click', (event) => {
    const option = event.target.closest('[role=option]');
    if (!option) return;
    document.getElementById('city-value').textContent = option.textContent.trim();
    document.getElementById('city').setAttribute('data-selected', option.textContent.trim());
    document.getElementById('city-list').hidden = true;
  });
</script>
"""


def test_browser_selects_unique_country_and_city_without_guessing():
    profile = ProfileView(
        candidate_id=7,
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+1 5550100123",
        location="Austin, TX",
        country="Canada",
    )
    live = plan_autofill(URL, MENU, [], profile)
    reviewed = reviewed_fields(live)
    decision = decide_fill(reviewed, live, included={item.field_id for item in live.ready}, overwrite=set(), attach_resume=False)
    assert any(action.field_id == "country" and action.value == "Canada" for action in decision.actions)
    assert any(action.field_id == "city" and action.value == "Austin, TX" for action in decision.actions)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(MENU)
        report = apply_actions(page, decision.actions, resume_field_id=None, resume_path=None, resume_name="")
        assert report.submitted is False
        assert page.evaluate("() => window.__submitted") is False
        assert page.locator("#first_name").input_value() == "Ada"
        assert page.locator("#email").input_value() == "ada@example.com"
        assert "selected Canada" in (page.locator("#flag").get_attribute("aria-label") or "")
        assert page.locator("#city-value").inner_text() == "Austin, Texas, United States"
        assert page.locator("#phone").input_value() == "5550100123"
        assert all(item.status == "filled" for item in report.outcomes)
        browser.close()
    shared = ProfileView(
        candidate_id=7,
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+1 5550100123",
        location="Austin",
    )
    ambiguous = plan_autofill(URL, MENU, [], shared)
    assert _field(ambiguous, "country").proposed_value == "+1"
    assert _field(ambiguous, "city").proposed_value == "Austin"
    refused = decide_fill(
        reviewed_fields(ambiguous),
        ambiguous,
        included={"country", "city"},
        overwrite=set(),
        attach_resume=False,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(MENU)
        report = apply_actions(page, refused.actions, resume_field_id=None, resume_path=None, resume_name="")
        assert report.submitted is False
        assert "selected" not in (page.locator("#flag").get_attribute("aria-label") or "")
        assert page.locator("#city-value").inner_text() == ""
        details = {item.field_id: item.detail for item in report.outcomes}
        assert "prefix" in details["country"]
        assert "Add the state" in details["city"]
        browser.close()


def _field(plan, field_id):
    for bucket in (plan.ready, plan.clarification, plan.missing_required, plan.unsupported):
        for item in bucket:
            if item.field_id == field_id:
                return item
    raise AssertionError(field_id)


def test_navigation_guard_blocks_other_origins():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><body>local-secret-page</body></html>"
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            install_navigation_guard(page)
            failed: list[str] = []
            page.on("requestfailed", lambda request: failed.append(request.url))
            try:
                page.goto(f"http://127.0.0.1:{port}/apply", timeout=3000)
            except Exception:
                pass
            assert any(f"127.0.0.1:{port}" in url for url in failed)
            browser.close()
    finally:
        server.shutdown()


def test_browser_keeps_selected_choices_and_fills_a_revealed_field(tmp_path):
    html = """
    <form id="application" onsubmit="window.__submitted = true; return false;">
      <label for="school">School</label>
      <select id="school" name="school"><option>Select</option><option>Example State University</option></select>
      <fieldset>
        <legend>Are you willing to relocate?</legend>
        <label><input type="radio" name="relocate" value="yes"> Yes</label>
        <label><input type="radio" name="relocate" value="no"> No</label>
      </fieldset>
      <fieldset>
        <legend>Open to relocation</legend>
        <label><input type="checkbox" name="cities" value="austin"> Austin</label>
        <label><input type="checkbox" name="cities" value="remote"> Remote</label>
      </fieldset>
      <label for="languages">Programming languages</label>
      <select id="languages" name="languages" multiple>
        <option>Python</option><option>SQL</option><option>Java</option>
      </select>
      <div class="select">
        <label for="team">Which team?</label>
        <input id="team" role="combobox" aria-controls="team-list" aria-label="Which team?">
        <div id="team-value" class="select__single-value"></div>
      </div>
      <ul id="team-list" role="listbox" hidden>
        <li role="option">Payments</li>
        <li role="option">Infra</li>
      </ul>
      <label for="track">Track</label>
      <select id="track" name="track">
        <option>Select</option>
        <option>Backend</option>
      </select>
      <div id="major-wrap" hidden>
        <label for="major">Major</label>
        <input id="major" name="major">
      </div>
      <button type="submit">Submit application</button>
    </form>
    <script>
      window.__submitted = false;
      const team = document.getElementById('team');
      team.addEventListener('input', () => { document.getElementById('team-list').hidden = false; });
      document.getElementById('team-list').addEventListener('click', (event) => {
        const option = event.target.closest('[role="option"]');
        if (!option) return;
        const text = option.textContent.trim();
        document.getElementById('team-value').textContent = text;
        team.value = text;
        document.getElementById('team-list').hidden = true;
      });
      document.getElementById('track').addEventListener('change', () => {
        if (document.getElementById('track').value === 'Backend') document.getElementById('major-wrap').hidden = false;
      });
    </script>
    """
    actions = [
        FillAction("school", "select", "school", "school", "School", "Example State University", "contact"),
        FillAction("relocate", "radio", "relocate", "", "Are you willing to relocate?", "Yes", "answer"),
        FillAction("cities", "checkboxes", "cities", "", "Open to relocation", "Austin\nRemote", "answer"),
        FillAction("languages", "multi_select", "languages", "languages", "Programming languages", "Python\nSQL", "answer"),
        FillAction("team", "combobox", "team", "team", "Which team?", "Payments", "answer"),
        FillAction("track", "select", "track", "track", "Track", "Backend", "contact"),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        report = apply_actions(page, actions, resume_field_id=None, resume_path=None, resume_name="")
        assert report.submitted is False
        assert page.evaluate("() => window.__submitted") is False
        assert all(item.status == "filled" for item in report.outcomes), [(item.label, item.detail) for item in report.outcomes]
        assert page.locator("#school").input_value() == "Example State University"
        assert page.locator('input[name="relocate"][value="yes"]').is_checked()
        assert page.locator('input[name="cities"][value="austin"]').is_checked()
        assert page.locator('input[name="cities"][value="remote"]').is_checked()
        selected = page.locator("#languages").evaluate("el => [...el.selectedOptions].map(option => option.text.trim())")
        assert selected == ["Python", "SQL"]
        assert page.locator("#team-value").inner_text() == "Payments"
        assert page.locator("#major-wrap").is_hidden() is False
        follow = apply_actions(
            page,
            [FillAction("major", "text", "major", "major", "Major", "Computer Science", "contact")],
            resume_field_id=None,
            resume_path=None,
            resume_name="",
        )
        assert follow.outcomes[0].status == "filled"
        assert page.locator("#major").input_value() == "Computer Science"
        assert page.locator("#school").input_value() == "Example State University"
        assert page.evaluate("() => window.__submitted") is False
        browser.close()


def test_browser_token_is_required_before_a_session_route_runs():
    app = FastAPI()

    @app.post("/api/autofill/sessions")
    def open_session(_: None = Depends(require_browser_token)):
        return {"opened": True}

    client = TestClient(app)
    denied = client.post("/api/autofill/sessions")
    assert denied.status_code == 401
    assert "ada@" not in denied.text
    allowed = client.post("/api/autofill/sessions", headers={"X-CareerPilot-Token": load_or_create_token()})
    assert allowed.status_code == 200
