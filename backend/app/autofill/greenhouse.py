"""Detect fields on a Greenhouse application page.

Classification uses the accessible label, autocomplete, and the control's
name or id. CSS class names are not used to decide what a field means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.autofill.html_dom import Node, by_id, parse_html, text_of, walk
from app.autofill.urls import ApplyUrl, classify_apply_url

_CONTROL_TAGS = frozenset({"input", "textarea", "select"})
_SKIP_INPUT_TYPES = frozenset({"hidden", "submit", "button", "image", "reset"})
_STANDARD = frozenset(
    {
        "first_name",
        "last_name",
        "email",
        "phone",
        "location",
        "resume",
        "linkedin",
        "github",
        "portfolio",
        "cover_letter",
    }
)
_AUTOCOMPLETE = {
    "given-name": "first_name",
    "family-name": "last_name",
    "email": "email",
    "tel": "phone",
    "tel-national": "phone",
}
_LABELS = {
    "first name": "first_name",
    "given name": "first_name",
    "last name": "last_name",
    "family name": "last_name",
    "surname": "last_name",
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile phone": "phone",
    "location": "location",
    "current location": "location",
    "resume": "resume",
    "resume cv": "resume",
    "cv": "resume",
    "linkedin": "linkedin",
    "linkedin profile": "linkedin",
    "linkedin url": "linkedin",
    "github": "github",
    "github profile": "github",
    "github url": "github",
    "portfolio": "portfolio",
    "portfolio url": "portfolio",
    "website": "portfolio",
    "personal website": "portfolio",
    "cover letter": "cover_letter",
}
_NAME_TOKENS = {
    "first": "first_name",
    "firstname": "first_name",
    "last": "last_name",
    "lastname": "last_name",
    "email": "email",
    "phone": "phone",
    "resume": "resume",
    "cv": "resume",
    "linkedin": "linkedin",
    "github": "github",
    "portfolio": "portfolio",
    "website": "portfolio",
    "location": "location",
    "cover": "cover_letter",
}
_SENSITIVE = (
    "work authorization",
    "authorized to work",
    "sponsorship",
    "visa status",
    "disability",
    "veteran",
    "gender",
    "race",
    "ethnicity",
    "demographic",
    "pronouns",
    "criminal",
    "felony",
)
_CAPTCHA = ("g-recaptcha", "h-captcha", "cf-turnstile", "recaptcha", "hcaptcha")
_MFA = ("one-time code", "verification code", "multi-factor", "two-factor")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class DetectedField:
    field_id: str
    semantic: str
    input_type: str
    label: str
    required: bool | None
    options: list[str] = field(default_factory=list)
    name: str = ""
    element_id: str = ""
    confidence: str = "low"
    current_value: str | None = None
    accept: str = ""


@dataclass
class FormDetection:
    url: str
    provider: str
    supported: bool
    rejection_reason: str | None
    form_found: bool
    fields: list[DetectedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    board_token: str | None = None
    job_id: str | None = None


def detect_application(url: str, html: str = "") -> FormDetection:
    decision = classify_apply_url(url)
    if not decision.supported:
        return FormDetection(
            url=decision.raw,
            provider=decision.provider,
            supported=False,
            rejection_reason=decision.reason,
            form_found=False,
        )
    return _detect_greenhouse(decision, html or "")


def _detect_greenhouse(decision: ApplyUrl, html: str) -> FormDetection:
    root = parse_html(html)
    blockers = _blockers(html)
    forms = [node for node in walk(root) if node.tag == "form"]
    scope, form_found, warnings = _choose_scope(root, forms)
    controls = _controls(scope)
    fields = _to_fields(controls, by_id(root), root)
    if any(node.tag == "button" or (node.tag == "input" and node.get("type").casefold() == "submit") for node in walk(scope)):
        warnings.append("A submit control is present. CareerPilot will not use it.")
    if not fields and form_found:
        warnings.append("The application form had no recognizable fields.")
    return FormDetection(
        url=decision.raw,
        provider="greenhouse",
        supported=True,
        rejection_reason=None,
        form_found=form_found,
        fields=fields,
        warnings=warnings,
        blockers=blockers,
        board_token=decision.board_token,
        job_id=decision.job_id,
    )


def _blockers(html: str) -> list[str]:
    lowered = html.casefold()
    found = []
    if any(marker in lowered for marker in _CAPTCHA):
        found.append("captcha")
    if any(marker in lowered for marker in _MFA):
        found.append("mfa")
    return found


def _choose_scope(root: Node, forms: list[Node]) -> tuple[Node, bool, list[str]]:
    if not forms:
        controls = _controls(root)
        if controls:
            return root, False, ["Form controls were found outside a form element."]
        return root, False, ["No application form was found."]
    ranked = sorted(forms, key=lambda form: (-_standard_score(form), 0 if "application" in form.get("id").casefold() else 1))
    warnings = []
    if len(forms) > 1:
        warnings.append("Multiple forms were present. Detection used the application form.")
    return ranked[0], True, warnings


def _standard_score(scope: Node) -> int:
    return sum(1 for control in _controls(scope) if _semantic_from_name(control.get("name") or control.get("id")) in _STANDARD)


def _controls(scope: Node) -> list[Node]:
    found = []
    for node in walk(scope):
        if node.tag not in _CONTROL_TAGS:
            continue
        if node.tag == "input" and node.get("type").casefold() in _SKIP_INPUT_TYPES:
            continue
        found.append(node)
    return found


def _to_fields(controls: list[Node], ids: dict[str, Node], root: Node) -> list[DetectedField]:
    groups: list[list[Node]] = []
    grouped: dict[str, list[Node]] = {}
    order = {id(control): index for index, control in enumerate(controls)}
    for control in controls:
        input_type = _input_type(control)
        name = control.get("name")
        if input_type in {"radio", "checkbox"} and name:
            grouped.setdefault(name, []).append(control)
        else:
            groups.append([control])
    groups.extend(grouped.values())
    groups.sort(key=lambda members: order[id(members[0])])

    fields: list[DetectedField] = []
    seen_standard: set[str] = set()
    for members in groups:
        primary = members[0]
        label, label_source = _question_label(members, ids, root)
        semantic, confidence = _classify(primary, label, label_source)
        if semantic in _STANDARD and semantic in seen_standard:
            semantic = "unknown"
            confidence = "low"
        if semantic in _STANDARD:
            seen_standard.add(semantic)
        required = _required(primary, label) if label or primary.has("required") or primary.get("aria-required") else None
        if any(_required(member, label) for member in members):
            required = True
        options = _options(members, ids, root)
        field_id = primary.get("name") or primary.get("id") or f"field-{len(fields) + 1}"
        fields.append(
            DetectedField(
                field_id=field_id,
                semantic=semantic,
                input_type=_input_type(primary),
                label=label,
                required=required,
                options=options,
                name=primary.get("name"),
                element_id=primary.get("id"),
                confidence=confidence,
                current_value=_current_value(members, ids, root),
                accept=primary.get("accept").strip() if _input_type(primary) == "file" else "",
            )
        )
    return fields


def _input_type(node: Node) -> str:
    if node.tag == "textarea":
        return "textarea"
    if node.tag == "select":
        return "select"
    raw = node.get("type").casefold() or "text"
    if raw in {"email", "tel", "url", "file", "checkbox", "radio", "text", "number"}:
        return raw
    return "text"


def _question_label(members: list[Node], ids: dict[str, Node], root: Node) -> tuple[str, str]:
    if len(members) > 1:
        parent = members[0].parent
        while parent is not None:
            if parent.tag == "fieldset":
                legend = next(
                    (child for kind, child in parent.events if kind == "el" and getattr(child, "tag", "") == "legend"),
                    None,
                )
                if legend is not None and text_of(legend):
                    return text_of(legend), "legend"
            parent = parent.parent
    return _label_for(members[0], ids, root)


def _label_for(node: Node, ids: dict[str, Node], root: Node) -> tuple[str, str]:
    labelledby = node.get("aria-labelledby")
    if labelledby:
        parts = [text_of(ids[item]) for item in labelledby.split() if item in ids]
        text = " ".join(part for part in parts if part).strip()
        if text:
            return text, "aria-labelledby"
    if node.get("aria-label").strip():
        return node.get("aria-label").strip(), "aria-label"
    element_id = node.get("id")
    if element_id:
        for candidate in walk(root):
            if candidate.tag == "label" and candidate.get("for") == element_id:
                return text_of(candidate), "label"
    parent = node.parent
    while parent is not None:
        if parent.tag == "label":
            return text_of(parent), "label"
        if parent.tag == "fieldset":
            legend = next((child for kind, child in parent.events if kind == "el" and child.tag == "legend"), None)  # type: ignore[union-attr]
            if legend is not None and text_of(legend):
                return text_of(legend), "legend"
        parent = parent.parent
    if node.get("placeholder").strip():
        return node.get("placeholder").strip(), "placeholder"
    return "", ""


def _classify(node: Node, label: str, label_source: str) -> tuple[str, str]:
    normalized = _normalize_label(label)
    sensitive = _sensitive(normalized)
    if sensitive:
        return "sensitive", "high" if label_source and label_source != "placeholder" else "low"
    auto = _AUTOCOMPLETE.get(node.get("autocomplete").casefold())
    if auto:
        return auto, "high"
    from_label = _from_label(normalized)
    if from_label:
        return from_label, "low" if label_source == "placeholder" else "high"
    from_name = _semantic_from_name(node.get("name") or node.get("id"))
    if from_name:
        return from_name, "high"
    if normalized.endswith("?") or len(normalized.split()) >= 6:
        return "custom_question", "high" if label_source and label_source != "placeholder" else "low"
    if "answers" in _TOKEN_RE.findall(node.get("name").casefold()):
        return "custom_question", "low"
    return "unknown", "low"


def _from_label(normalized: str) -> str | None:
    if normalized in _LABELS:
        return _LABELS[normalized]
    words = set(normalized.split())
    if "linkedin" in words:
        return "linkedin"
    if "github" in words:
        return "github"
    if "portfolio" in words:
        return "portfolio"
    if words & {"resume", "cv"} and len(words) <= 4:
        return "resume"
    return None


def _semantic_from_name(value: str) -> str | None:
    tokens = _TOKEN_RE.findall(value.casefold().replace("first_name", "firstname").replace("last_name", "lastname"))
    if "firstname" in tokens or ({"first", "name"} <= set(tokens)):
        return "first_name"
    if "lastname" in tokens or ({"last", "name"} <= set(tokens)):
        return "last_name"
    if "cover" in tokens and "letter" in tokens:
        return "cover_letter"
    for token in tokens:
        mapped = _NAME_TOKENS.get(token)
        if mapped and token not in {"first", "last", "cover"}:
            return mapped
    return None


def _sensitive(normalized: str) -> bool:
    return any(phrase in normalized for phrase in _SENSITIVE)


def _normalize_label(label: str) -> str:
    text = label.replace("*", " ").replace("/", " ")
    text = re.sub(r"\(required\)", " ", text, flags=re.I)
    text = re.sub(r"[^a-z0-9 ]", " ", text.casefold())
    return " ".join(text.split())


def _required(node: Node, label: str) -> bool:
    if node.has("required") or node.get("aria-required").casefold() == "true":
        return True
    return "*" in label or bool(re.search(r"\(required\)", label, flags=re.I))


def _current_value(members: list[Node], ids: dict[str, Node], root: Node) -> str | None:
    """Read a value the page already has. File paths are ignored."""
    primary = members[0]
    if _input_type(primary) == "file":
        return None
    if primary.tag == "textarea":
        return text_of(primary).strip() or None
    if primary.tag == "select":
        selected = [text_of(node) for node in walk(primary) if node.tag == "option" and node.has("selected")]
        return selected[0].strip() if selected and selected[0].strip() else None
    if _input_type(primary) in {"radio", "checkbox"}:
        chosen = []
        for member in members:
            if not member.has("checked"):
                continue
            label, _source = _label_for(member, ids, root)
            chosen.append(label or member.get("value").strip())
        chosen = [item for item in chosen if item]
        return ", ".join(chosen) or None
    return primary.get("value").strip() or None


def _options(members: list[Node], ids: dict[str, Node], root: Node) -> list[str]:
    primary = members[0]
    if primary.tag == "select":
        return [text_of(node) for node in walk(primary) if node.tag == "option" and text_of(node)]
    if len(members) > 1 or _input_type(primary) in {"radio", "checkbox"}:
        labels = []
        for member in members:
            label, _source = _label_for(member, ids, root)
            if label and label not in labels:
                labels.append(label)
        return labels
    return []
