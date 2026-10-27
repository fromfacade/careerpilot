"""One explicit Greenhouse submission.

Filling never calls this module. A click happens only after the caller has
confirmed this preparation and this page, and only when exactly one submit
control is identifiable. A click is not treated as success.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from app.autofill.actions import SubmissionBlocked
from app.autofill.html_dom import parse_html, text_of, walk
from app.autofill.urls import same_greenhouse_application

_SUBMIT_LABELS = frozenset({"submit", "submit application", "submit your application"})
_SUCCESS = (
    "thank you for applying",
    "application has been submitted",
    "your application has been received",
    "we have received your application",
    "your application was submitted",
)
_FAILURE = (
    "there was a problem submitting",
    "could not submit your application",
    "please fix the errors",
    "this field is required",
    "submission failed",
    "unable to submit",
)
_SAFE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_EMAIL = re.compile(r"\S+@\S+")
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_OUTCOME_JS = """() => {
  const text = (document.body && document.body.innerText || '').toLowerCase();
  const phrases = [
    'thank you for applying',
    'application has been submitted',
    'your application has been received',
    'we have received your application',
    'your application was submitted',
    'please fix the errors',
    'this field is required',
    'submission failed',
    'unable to submit',
    'could not submit your application',
    'there was a problem submitting'
  ];
  return phrases.some((phrase) => text.includes(phrase));
}"""


class SubmissionGate:
    """One in-flight submission for a browser session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.held = False

    def acquire(self) -> bool:
        with self._lock:
            if self.held:
                return False
            self.held = True
            return True

    def release(self) -> None:
        with self._lock:
            self.held = False


@dataclass(frozen=True)
class SubmitControl:
    element_id: str
    name: str
    label: str


@dataclass
class PrepareResult:
    ok: bool
    detail: str
    control: SubmitControl | None = None


@dataclass
class ClickResult:
    clicked: bool
    html: str
    timed_out: bool
    error: str = ""


def authorization_problem(
    *,
    confirm: bool,
    preparation_id: int,
    apply_url: str,
    session_preparation_id: int,
    session_apply_url: str,
    expires_at: datetime | None,
    now: datetime,
) -> str | None:
    """Return a reason to refuse, or None when this confirmation matches the open session."""
    if not confirm:
        return "Submission was not confirmed."
    if preparation_id != session_preparation_id or (apply_url or "") != (session_apply_url or ""):
        return "That confirmation belongs to a different application."
    if expires_at is None:
        return "Submission was not authorized for this browser session."
    if now >= expires_at:
        return "The submission confirmation expired. Review this application and confirm again."
    return None


def prepare_submission(
    html: str,
    *,
    page_url: str,
    expected_url: str,
    readiness_status: str,
    failing_details: list[str],
    blockers: list[str],
    already_submitted: bool | None,
) -> PrepareResult:
    """Decide whether the live page may be submitted. This does not click."""
    if readiness_status != "ready_to_submit":
        detail = _public(" ".join(failing_details)) or "A readiness check did not pass."
        return PrepareResult(False, f"The application is no longer ready to submit. {detail}")
    if any(item in {"captcha", "mfa"} for item in blockers):
        return PrepareResult(False, "A CAPTCHA or sign-in challenge is active. CareerPilot will not submit.")
    if already_submitted is True:
        return PrepareResult(False, "The employer page shows this application was already submitted.")
    if already_submitted is None:
        return PrepareResult(False, "CareerPilot could not verify that this application is still unsubmitted.")
    matches, detail = same_greenhouse_application(page_url, expected_url)
    if not matches:
        return PrepareResult(False, detail)
    controls = find_submit_controls(html)
    if not controls:
        return PrepareResult(False, "No application submit control was found, so nothing was sent.")
    if len(controls) > 1:
        return PrepareResult(False, "More than one submit control is on the page, so none was used.")
    return PrepareResult(True, "", controls[0])


def find_submit_controls(html: str) -> list[SubmitControl]:
    root = parse_html(html)
    found: list[SubmitControl] = []
    for node in walk(root):
        if node.tag not in {"button", "input"} or _concealed(node):
            continue
        kind = node.get("type").casefold()
        if node.tag == "input" and kind != "submit":
            continue
        if node.tag == "button" and kind not in {"", "submit"}:
            continue
        label = _label(node)
        if label not in _SUBMIT_LABELS:
            continue
        element_id = node.get("id")
        name = node.get("name")
        if not (_SAFE.fullmatch(element_id) or _SAFE.fullmatch(name)):
            continue
        found.append(SubmitControl(element_id=element_id if _SAFE.fullmatch(element_id) else "", name=name, label=label))
    return found


def click_authorized_submit(page: Page, control: SubmitControl, *, authorized: bool, timeout_ms: int = 8_000) -> ClickResult:
    if not authorized:
        raise SubmissionBlocked("Submission was not authorized.")
    selector = f'[id="{control.element_id}"]' if control.element_id else f'[name="{control.name}"]'
    locator = page.locator(selector)
    if locator.count() != 1:
        return ClickResult(False, page.content(), False, "The submit control was not uniquely on the page. Nothing was sent.")
    visible = _norm(locator.first.inner_text() or locator.first.get_attribute("value") or "")
    if visible not in _SUBMIT_LABELS:
        return ClickResult(False, page.content(), False, "The submit control label changed, so it was not used.")
    try:
        locator.click(timeout=5_000)
    except PlaywrightTimeout:
        return ClickResult(False, page.content(), False, "The submit control could not be clicked. Nothing was sent.")
    timed_out = False
    try:
        page.wait_for_function(_OUTCOME_JS, timeout=timeout_ms)
    except PlaywrightTimeout:
        timed_out = True
    return ClickResult(True, page.content(), timed_out)


def interpret_submission(html: str, *, clicked: bool, timed_out: bool) -> tuple[str, str]:
    """Map the page after a click to submitted, submission_failed, or confirmation_unknown."""
    if not clicked:
        return "submission_failed", "The submit control was not used. Nothing was sent."
    text = _visible(html)
    if any(phrase in text for phrase in _SUCCESS):
        return "submitted", "The employer page confirmed the application was received."
    if any(phrase in text for phrase in _FAILURE):
        return "submission_failed", "The employer page reported a problem and did not confirm receipt. CareerPilot will not retry."
    if timed_out:
        return (
            "confirmation_unknown",
            "The page did not show whether the application was received. Check the employer page. CareerPilot will not retry.",
        )
    return (
        "confirmation_unknown",
        "The page did not show a success or failure confirmation. Check the employer page. CareerPilot will not retry.",
    )


def _label(node) -> str:
    if node.tag == "input":
        return _norm(node.get("value") or "submit")
    return _norm(text_of(node))


def _norm(value: str) -> str:
    return " ".join((value or "").replace("*", " ").casefold().split())


def _concealed(node) -> bool:
    current = node
    while current is not None and current.tag != "document":
        style = current.get("style").casefold().replace(" ", "")
        if current.has("hidden") or current.get("aria-hidden").casefold() == "true":
            return True
        if "display:none" in style or "visibility:hidden" in style:
            return True
        current = current.parent
    return False


def _visible(html: str) -> str:
    text = _TAG.sub(" ", _STYLE.sub(" ", _SCRIPT.sub(" ", html or "")))
    return " ".join(text.casefold().split())


def _public(value: str) -> str:
    text = " ".join((value or "").split())
    return _EMAIL.sub("[redacted]", text)[:400]
