"""Fill a Greenhouse page that is already open. Does not submit it.

Locators use the control id or name. Class names are not used. File bytes
are handed to Chromium through Playwright; the storage directory is not
written into the page.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from app.autofill.actions import FillAction, SubmissionBlocked, refuse_submission
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
        if action.input_type == "select":
            locator.first.select_option(label=action.value)
        elif action.input_type == "radio":
            _choose_grouped(page, action, "radio")
        elif action.input_type == "checkbox":
            _choose_grouped(page, action, "checkbox")
        elif action.input_type == "file":
            return FieldOutcome(action.field_id, action.label, "failed", "Resume files use the attachment step.")
        else:
            locator.first.fill(action.value)
        if not _verified(page, action):
            return FieldOutcome(action.field_id, action.label, "failed", "The form value does not match the reviewed plan.")
    except SubmissionBlocked:
        raise
    except Exception:
        return FieldOutcome(action.field_id, action.label, "failed", "The field could not be filled.")
    return FieldOutcome(action.field_id, action.label, "filled", "Verified.")


def _attach(page: Page, field_id: str, path: str | None, display_name: str) -> tuple[str, str]:
    if not path:
        return "failed", "The selected resume file is missing."
    locator = page.locator(f'input[type="file"][name="{_escape(field_id)}"], input[type="file"][id="{_escape(field_id)}"]')
    if locator.count() == 0:
        return "failed", "The resume upload is no longer on the page."
    try:
        locator.first.set_input_files(path)
        kept = locator.first.evaluate("el => el.files ? el.files.length : 0")
    except Exception:
        return "failed", "The browser did not accept the resume file."
    if kept != 1:
        return "failed", "The form did not keep the resume file."
    return "attached", f"Attached {display_name}."


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
    return actual.strip().casefold() == action.value.strip().casefold()


def _document_allowed(url: str) -> bool:
    if url in _ABOUT or url.startswith("about:"):
        return True
    return navigation_allowed(url)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
