"""Detect fields on a Greenhouse application page.

Classification uses the accessible label, autocomplete, and the control's
name or id. CSS class names are not used to decide what a field means.
`question_kind` names common application questions. It does not invent an
answer or choose a value.
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
        "phone_country",
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
    "city": "location",
    "location city": "location",
    "country": "phone_country",
    "country code": "phone_country",
    "phone country": "phone_country",
    "school": "school",
    "school name": "school",
    "university": "school",
    "degree": "degree",
    "highest degree": "degree",
    "discipline": "discipline",
    "major": "discipline",
    "field of study": "discipline",
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
    "city": "location",
    "country": "phone_country",
    "school": "school",
    "degree": "degree",
    "discipline": "discipline",
    "major": "discipline",
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
    "gender identity",
    "transgender",
    "hispanic",
    "latino",
    "latina",
    "sexual orientation",
    "veteran status",
    "protected veteran",
    "disability status",
    "self identification",
)
_CONSENT = (
    "i agree",
    "i certify",
    "i acknowledge",
    "i consent",
    "terms and conditions",
    "privacy policy",
    "privacy notice",
    "by checking this",
    "electronic signature",
    "e signature",
    "legal declaration",
)
_FACT_KINDS = {
    "school": "school",
    "degree": "degree",
    "major": "discipline",
    "github": "github",
    "portfolio": "portfolio",
}
_ANSWER_KINDS = frozenset(
    {
        "graduation_date",
        "gpa",
        "start_date",
        "relocation",
        "current_employer",
        "experience",
        "written_question",
    }
)
_SCHOOL_EXACT = frozenset(
    {
        "school",
        "current school",
        "school name",
        "university",
        "current university",
        "university name",
        "college",
        "college name",
        "name of school",
        "name of university",
        "school attending",
        "what school do you attend",
        "what university do you attend",
        "which school do you attend",
        "which university do you attend",
    }
)
_DEGREE_EXACT = frozenset(
    {
        "degree",
        "highest degree",
        "degree type",
        "current degree",
        "degree name",
        "what degree are you pursuing",
        "highest level of education",
        "education level",
        "high school diploma",
    }
)
_MAJOR_EXACT = frozenset(
    {
        "major",
        "discipline",
        "field of study",
        "area of study",
        "current major",
        "concentration",
        "course of study",
        "what is your major",
    }
)
_GRADUATION = (
    "graduation date",
    "date of graduation",
    "graduation month",
    "graduation year",
    "expected graduation",
    "anticipated graduation",
    "when do you graduate",
    "when did you graduate",
    "when will you graduate",
    "grad date",
)
_START = (
    "start date",
    "earliest start",
    "available start",
    "availability date",
    "date available",
    "when can you start",
    "when are you available",
    "available to start",
)
_START_EXCLUDED = (
    "employment start",
    "job start",
    "position start",
    "previous start",
    "start date of",
)
_EMPLOYER = (
    "current employer",
    "current company",
    "present employer",
    "most recent employer",
    "most recent company",
    "current organization",
)
_EXPERIENCE = (
    "relevant experience",
    "work experience",
    "related experience",
    "professional experience",
    "years of experience",
    "years of relevant experience",
)
_WRITTEN_EXACT = frozenset({"additional information", "additional comments", "anything else"})
_WRITTEN_PREFIX = ("why ", "how ", "what ", "describe ", "tell us ", "tell me ", "explain ", "please ")
_CAPTCHA_WIDGETS = ("g-recaptcha", "h-captcha", "cf-turnstile", "hcaptcha")
_CAPTCHA_CHALLENGE = ("bframe", "hcaptcha.com", "challenges.cloudflare.com")
_MFA = ("one-time code", "verification code", "multi-factor", "two-factor")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
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
    question_kind: str = ""


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
    root = parse_html(html)
    found = []
    if _active_captcha(root):
        found.append("captcha")
    visible = text_of(root).casefold()
    if any(phrase in visible for phrase in _MFA):
        found.append("mfa")
    return found


def _active_captcha(root: Node) -> bool:
    """True only for a visible, unsolved challenge. A loaded script is not one."""
    solved = False
    visible_challenge = False
    for node in walk(root):
        if node.tag in {"script", "style", "noscript"}:
            continue
        if _captcha_solved(node):
            solved = True
            continue
        if not _captcha_widget(node):
            continue
        if _captcha_inactive(node) or _element_concealed(node) or _ancestor_concealed(node):
            continue
        visible_challenge = True
    return visible_challenge and not solved


def _captcha_widget(node: Node) -> bool:
    identity = " ".join((node.get("class"), node.get("id"), node.get("title"))).casefold()
    src = node.get("src").casefold()
    if any(marker in identity for marker in _CAPTCHA_WIDGETS):
        return True
    if node.tag == "iframe" and any(marker in src for marker in _CAPTCHA_CHALLENGE):
        return True
    title = node.get("title").casefold()
    return "challenge" in title and "captcha" in f"{title} {src}"


def _captcha_inactive(node: Node) -> bool:
    if node.get("data-size").casefold() == "invisible":
        return True
    identity = f"{node.get('class')} {node.get('id')}".casefold()
    return "grecaptcha-badge" in identity or "rc-anchor" in identity


def _captcha_solved(node: Node) -> bool:
    identity = f"{node.get('name')} {node.get('id')}".casefold()
    if "g-recaptcha-response" not in identity and "h-captcha-response" not in identity:
        return False
    return bool(node.get("value").strip() or text_of(node).strip())


def _element_concealed(node: Node) -> bool:
    if node.has("hidden") or node.get("aria-hidden").casefold() == "true":
        return True
    return bool(_HIDDEN_STYLE.search(node.get("style")))


def _ancestor_concealed(node: Node) -> bool:
    parent = node.parent
    while parent is not None and parent.tag != "document":
        if _element_concealed(parent):
            return True
        parent = parent.parent
    return False


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
        if node.tag in {"script", "style", "noscript"} or _ancestor_concealed(node):
            continue
        custom_dropdown = node.get("role").casefold() == "combobox" and node.tag not in _CONTROL_TAGS
        if node.tag not in _CONTROL_TAGS and not custom_dropdown:
            continue
        if node.tag == "input" and node.get("type").casefold() in _SKIP_INPUT_TYPES:
            continue
        if _element_concealed(node) and _input_type(node) != "file":
            continue
        if _decorative(node):
            continue
        found.append(node)
    return found


def _decorative(node: Node) -> bool:
    role = node.get("role").casefold()
    if role in {"searchbox", "presentation", "none"}:
        return True
    if node.get("type").casefold() == "search" and not node.get("name"):
        return True
    return node.get("tabindex") == "-1" and not node.get("name") and role != "combobox"


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
        if _phone_country(primary, label):
            semantic, confidence = "phone_country", "high" if label_source and label_source != "placeholder" else "low"
        else:
            semantic, confidence = _classify(primary, label, label_source)
        question_kind = _question_kind(label, _normalize_label(label))
        if semantic == "sensitive":
            question_kind = "sensitive"
        elif semantic == "discipline" and not question_kind:
            question_kind = "major"
        elif semantic in {"school", "degree", "github", "portfolio"} and not question_kind:
            question_kind = semantic
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
                question_kind=question_kind,
            )
        )
    return _dedupe(fields)


def _phone_country(node: Node, label: str) -> bool:
    text = _normalize_label(f"{label} {node.get('name')} {node.get('id')} {node.get('aria-label')}")
    if not any(token in text.split() for token in ("country", "dial", "calling")):
        return False
    parent = node.parent
    for _ in range(4):
        if parent is None:
            return False
        for child in walk(parent):
            if child is node:
                continue
            identity = f"{child.get('name')} {child.get('id')} {child.get('type')}".casefold()
            if "phone" in identity or child.get("type").casefold() == "tel":
                return True
        parent = parent.parent
    return False


def _dedupe(fields: list[DetectedField]) -> list[DetectedField]:
    unique: list[DetectedField] = []
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    for item in fields:
        name = item.name.strip()
        element_id = item.element_id.strip()
        if name and name in seen_names:
            continue
        if element_id and element_id in seen_ids:
            continue
        if not item.label.strip() and not name and item.semantic == "unknown":
            continue
        if name:
            seen_names.add(name)
        if element_id:
            seen_ids.add(element_id)
        unique.append(item)
    named_labels = {_normalize_label(item.label) for item in unique if item.name.strip() and _normalize_label(item.label)}
    kept: list[DetectedField] = []
    seen_unnamed: set[str] = set()
    for item in unique:
        label = _normalize_label(item.label)
        if not item.name.strip() and label and (label in named_labels or label in seen_unnamed):
            continue
        if not item.name.strip() and label:
            seen_unnamed.add(label)
        kept.append(item)
    return kept


def _input_type(node: Node) -> str:
    if node.tag == "textarea":
        return "textarea"
    if node.tag == "input" and node.get("role").casefold() == "combobox":
        return "combobox"
    if node.tag == "select" or node.get("role").casefold() == "combobox":
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
    confidence = "low" if not label_source or label_source == "placeholder" else "high"
    if _sensitive(normalized) or _consent_label(normalized):
        return "sensitive", confidence
    auto = _AUTOCOMPLETE.get(node.get("autocomplete").casefold())
    if auto:
        return auto, "high"
    kind = _question_kind(label, normalized)
    linked = _FACT_KINDS.get(kind)
    if linked and not _link_username(kind, normalized):
        return linked, confidence
    from_label = _from_label(normalized)
    if from_label:
        return from_label, confidence
    from_name = _semantic_from_name(node.get("name") or node.get("id"))
    if from_name:
        return from_name, "high"
    if kind in _ANSWER_KINDS:
        return "custom_question", confidence
    if normalized.endswith("?") or len(normalized.split()) >= 6:
        return "custom_question", confidence
    if "answers" in _TOKEN_RE.findall(node.get("name").casefold()):
        return "custom_question", "low"
    return "unknown", "low"


def _question_kind(label: str, normalized: str) -> str:
    """Name a common question. An empty result means the label is not one of them."""
    if not normalized or _sensitive(normalized) or _consent_label(normalized):
        return ""
    if _matches_graduation(normalized):
        return "graduation_date"
    if "gpa" in set(normalized.split()) or "grade point" in normalized:
        return "gpa"
    if _matches_start(normalized):
        return "start_date"
    if "relocat" in normalized:
        return "relocation"
    if any(phrase in normalized for phrase in _EMPLOYER):
        return "current_employer"
    if _matches_experience(normalized):
        return "experience"
    if normalized in _MAJOR_EXACT:
        return "major"
    if normalized in _DEGREE_EXACT:
        return "degree"
    if normalized in _SCHOOL_EXACT:
        return "school"
    words = normalized.split()
    wordset = set(words)
    if _is_link_label(wordset, words, "github"):
        return "github"
    if _is_link_label(wordset, words, "portfolio") or _is_website_label(wordset, words):
        return "portfolio"
    if _is_written_prompt(label, normalized):
        return "written_question"
    return ""


def _matches_graduation(normalized: str) -> bool:
    if "graduation requirement" in normalized:
        return False
    if normalized in {"graduation", "grad date"}:
        return True
    return any(phrase in normalized for phrase in _GRADUATION)


def _matches_start(normalized: str) -> bool:
    if any(phrase in normalized for phrase in _START_EXCLUDED):
        return False
    if normalized == "availability":
        return True
    return any(phrase in normalized for phrase in _START)


def _matches_experience(normalized: str) -> bool:
    if "experience with" in normalized:
        return False
    return any(phrase in normalized for phrase in _EXPERIENCE)


def _is_link_label(wordset: set[str], words: list[str], token: str) -> bool:
    if token not in wordset or len(words) > 6:
        return False
    return not wordset & {"describe", "experience", "project", "built"}


def _is_website_label(wordset: set[str], words: list[str]) -> bool:
    if "website" not in wordset or len(words) > 4:
        return False
    return not wordset & {"experience", "describe", "project"}


def _link_username(kind: str, normalized: str) -> bool:
    if kind not in {"github", "portfolio"}:
        return False
    words = set(normalized.split())
    return bool(words & {"username", "handle"})


def _is_written_prompt(label: str, normalized: str) -> bool:
    if "?" in label:
        return True
    if normalized in _WRITTEN_EXACT:
        return True
    return normalized.startswith(_WRITTEN_PREFIX)


def _consent_label(normalized: str) -> bool:
    return any(phrase in normalized for phrase in _CONSENT)


def _from_label(normalized: str) -> str | None:
    if normalized in _LABELS:
        return _LABELS[normalized]
    words = set(normalized.split())
    if words & {"username", "handle"} and words & {"linkedin", "github", "portfolio", "website"}:
        return None
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
    blocked = {"github", "portfolio", "website"} if {"username", "handle"} & set(tokens) else set()
    for token in tokens:
        mapped = _NAME_TOKENS.get(token)
        if mapped and token not in {"first", "last", "cover"} and token not in blocked and mapped not in blocked:
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
