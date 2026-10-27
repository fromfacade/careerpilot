"""Fill a Greenhouse page that is already open. Does not submit it.

Locators use the control id or name. Class names are not used. File bytes
are handed to Chromium through Playwright; the storage directory is not
written into the page.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from app.autofill.actions import FillAction, SubmissionBlocked, refuse_submission
from app.autofill.mapping import (
    _dial_prefix,
    explain_location_miss,
    location_query,
    match_listed_country,
    match_listed_location,
)
from app.autofill.materials import _upload_name
from app.autofill.urls import classify_apply_url, navigation_allowed

_ABOUT = {"about:blank", ""}


@dataclass
class FieldOutcome:
    field_id: str
    label: str
    status: str
    detail: str


@dataclass
class FillReport:
    outcomes: list[FieldOutcome] = field(default_factory=list)
    resume_status: str = "skipped"
    resume_detail: str = ""
    stopped: str | None = None
    submitted: bool = False
    unresolved: list[str] = field(default_factory=list)


def install_navigation_guard(page: Page) -> None:
    def guard(route) -> None:
        url = route.request.url
        if route.request.resource_type != "document" or _document_allowed(url):
            route.continue_()
            return
        route.abort()

    page.route("**/*", guard)


def open_application(page: Page, url: str, timeout_ms: int = 30_000) -> str:
    decision = classify_apply_url(url)
    if not decision.supported:
        raise NavigationBlocked(decision.reason or "That application URL is not supported.")
    install_navigation_guard(page)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeout as exc:
        raise NavigationBlocked("The application page did not load in time.") from exc
    final = page.url
    if not classify_apply_url(final).supported:
        raise NavigationBlocked("The browser left the Greenhouse application page.")
    return page.content()


def apply_actions(
    page: Page,
    actions: list[FillAction],
    *,
    resume_field_id: str | None,
    resume_path: str | None,
    resume_name: str,
    cancel: threading.Event | None = None,
) -> FillReport:
    refuse_submission("fill")
    report = FillReport(submitted=False)
    for action in actions:
        if cancel is not None and cancel.is_set():
            report.stopped = "cancelled"
            break
        report.outcomes.append(_fill_one(page, action))
    if report.stopped:
        return report
    if resume_field_id:
        report.resume_status, report.resume_detail = _attach(page, resume_field_id, resume_path, resume_name)
    return report


class NavigationBlocked(RuntimeError):
    pass


def _fill_one(page: Page, action: FillAction) -> FieldOutcome:
    if action.input_type in {"submit", "button"} or action.kind == "submit":
        raise SubmissionBlocked("CareerPilot does not submit applications.")
    locator = _locator(page, action)
    if locator is None or locator.count() == 0:
        return FieldOutcome(action.field_id, action.label, "failed", "The field is no longer on the page.")
    try:
        if action.input_type == "combobox":
            return _fill_combobox(page, locator.first, action)
        if action.input_type == "select":
            locator.first.select_option(label=action.value)
        elif action.input_type == "radio":
            _choose_grouped(page, action, "radio")
        elif action.input_type == "checkbox":
            _choose_grouped(page, action, "checkbox")
        elif action.input_type == "file":
            return FieldOutcome(action.field_id, action.label, "failed", "Resume files use the attachment step.")
        else:
            locator.first.fill(_phone_text(action) if action.input_type == "tel" else action.value)
        if not _verified(page, action):
            return FieldOutcome(action.field_id, action.label, "failed", "The form value does not match the reviewed plan.")
    except SubmissionBlocked:
        raise
    except Exception:
        return FieldOutcome(action.field_id, action.label, "failed", "The field could not be filled.")
    return FieldOutcome(action.field_id, action.label, "filled", "Verified.")


def _attach(page: Page, field_id: str, path: str | None, display_name: str) -> tuple[str, str]:
    file = Path(path) if path else None
    if file is None or not file.is_file():
        return "failed", "The selected resume file is missing."
    try:
        data = file.read_bytes()
    except OSError:
        return "failed", "The selected resume file is missing."
    present = _present_name(display_name, file.suffix)
    locator = page.locator(f'input[type="file"][name="{_escape(field_id)}"], input[type="file"][id="{_escape(field_id)}"]')
    if locator.count() == 0:
        return "failed", "The resume upload is no longer on the page."
    try:
        locator.first.set_input_files({"name": present, "mimeType": _mime(present), "buffer": data})
        info = locator.first.evaluate(
            """async (el) => {
                const file = el.files && el.files[0];
                if (!file) return null;
                const bytes = new Uint8Array(await file.arrayBuffer());
                let hex = '';
                for (const byte of bytes) hex += byte.toString(16).padStart(2, '0');
                return {name: file.name, hex};
            }"""
        )
    except Exception:
        return "failed", "The browser did not accept the resume file."
    if not info or info.get("name") != present or info.get("hex") != data.hex():
        return "failed", "The uploaded resume does not match the approved file."
    return "attached", f"Attached {present}."


def _present_name(name: str, suffix: str) -> str:
    cleaned = (name or "").strip()
    if cleaned.casefold().endswith((".pdf", ".docx")):
        return _upload_name(cleaned, cleaned.rsplit(".", 1)[-1])
    fmt = suffix.casefold().lstrip(".")
    return _upload_name(cleaned, fmt or "pdf")


def _mime(name: str) -> str:
    if name.casefold().endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/pdf"


def _locator(page: Page, action: FillAction):
    element_id = action.element_id or ""
    name = action.name or action.field_id
    if element_id:
        found = page.locator(f'[id="{_escape(element_id)}"]')
        if found.count():
            return found
    if name:
        return page.locator(f'[name="{_escape(name)}"]')
    return None


def _choose_grouped(page: Page, action: FillAction, input_type: str) -> None:
    name = action.name or action.field_id
    group = page.locator(f'input[type="{input_type}"][name="{_escape(name)}"]')
    count = group.count()
    wanted = action.value.strip().casefold()
    for index in range(count):
        item = group.nth(index)
        label = item.evaluate(
            """el => {
                const text = el.labels && el.labels[0] ? el.labels[0].innerText : '';
                return text || el.value || '';
            }"""
        )
        if str(label).strip().casefold() == wanted or (item.get_attribute("value") or "").strip().casefold() == wanted:
            item.check()
            return
    raise LookupError(action.field_id)


def _verified(page: Page, action: FillAction) -> bool:
    if action.input_type in {"radio", "checkbox"}:
        name = action.name or action.field_id
        group = page.locator(f'input[type="{action.input_type}"][name="{_escape(name)}"]:checked')
        if group.count() == 0:
            return False
        label = group.first.evaluate(
            """el => {
                const text = el.labels && el.labels[0] ? el.labels[0].innerText : '';
                return text || el.value || '';
            }"""
        )
        return str(label).strip().casefold() == action.value.strip().casefold() or (
            group.first.get_attribute("value") or ""
        ).strip().casefold() == action.value.strip().casefold()
    locator = _locator(page, action)
    if locator is None or locator.count() == 0:
        return False
    if action.input_type == "select":
        actual = locator.first.evaluate("el => el.selectedOptions[0] ? el.selectedOptions[0].text : ''")
        return str(actual).strip().casefold() == action.value.strip().casefold()
    actual = locator.first.input_value()
    if action.input_type == "tel":
        return _phone_matches(actual, action.value)
    return actual.strip().casefold() == action.value.strip().casefold()


def _fill_combobox(page: Page, locator, action: FillAction) -> FieldOutcome:
    search = _search_text(action)
    try:
        locator.click()
        locator.fill("")
        if search:
            locator.press_sequentially(search, delay=20)
        listbox = locator.get_attribute("aria-controls")
        options = page.locator(f'[id="{_escape(listbox)}"] [role="option"]') if listbox else page.locator('[role="option"]')
        texts, chosen = _wait_for_choice(page, options, action)
        if chosen is None:
            page.keyboard.press("Escape")
            return FieldOutcome(action.field_id, action.label, "failed", _no_match_reason(action, texts))
        options.nth(texts.index(chosen)).click()
        if not _combobox_verified(page, locator, action, chosen):
            return FieldOutcome(action.field_id, action.label, "failed", "The selected choice did not stay on the form.")
    except Exception:
        return FieldOutcome(action.field_id, action.label, "failed", "The dropdown could not be filled.")
    return FieldOutcome(action.field_id, action.label, "filled", "Verified.")


def _search_text(action: FillAction) -> str:
    if _is_location(action):
        return location_query(action.value)
    if action.value.strip().startswith("+"):
        return action.value.strip()
    return action.value.split("+", 1)[0].strip()


def _wait_for_choice(page: Page, options, action: FillAction) -> tuple[list[str], str | None]:
    options.first.wait_for(state="visible", timeout=4000)
    texts: list[str] = []
    chosen = None
    for _ in range(8):
        texts = [text.strip() for text in options.all_inner_texts() if text.strip()]
        chosen = _choose_option(action, texts)
        if chosen is not None:
            return texts, chosen
        page.wait_for_timeout(300)
    return texts, None


def _is_location(action: FillAction) -> bool:
    label = action.label.casefold()
    return "location" in label or "city" in label


def _choose_option(action: FillAction, options: list[str]) -> str | None:
    if _is_location(action):
        return match_listed_location(action.value, options)
    return match_listed_country(action.value, options)


def _no_match_reason(action: FillAction, options: list[str]) -> str:
    if _is_location(action):
        return explain_location_miss(action.value, options)
    if action.value.strip().startswith("+"):
        return "More than one country uses this phone prefix, so none was selected."
    return "No listed choice exactly matches the verified country."


def _combobox_verified(page: Page, locator, action: FillAction, chosen: str) -> bool:
    if _is_location(action):
        shown = locator.evaluate(
            """el => {
                const root = el.closest('.select') || el.parentElement;
                const single = root ? root.querySelector('[class*="single-value"]') : null;
                return (single && single.textContent) || el.getAttribute('data-selected') || '';
            }"""
        )
        return str(shown).strip().casefold() == chosen.strip().casefold()
    country = chosen.split("+", 1)[0].strip()
    button = page.locator("button[aria-label*='selected']")
    if button.count() == 0:
        return False
    aria = button.last.get_attribute("aria-label") or ""
    return f"selected {country}".casefold() in aria.casefold()


def _phone_text(action: FillAction) -> str:
    text = action.value.strip()
    prefix = _dial_prefix(text)
    if prefix and text.startswith(prefix):
        text = text[len(prefix):].strip()
    digits = "".join(char for char in text if char.isdigit())
    return digits or text


def _phone_matches(actual: str, expected: str) -> bool:
    found = "".join(char for char in actual if char.isdigit())
    wanted = "".join(char for char in expected if char.isdigit())
    return bool(found) and (found == wanted or (wanted.endswith(found) and len(found) >= 7))


def _document_allowed(url: str) -> bool:
    if url in _ABOUT or url.startswith("about:"):
        return True
    return navigation_allowed(url)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
