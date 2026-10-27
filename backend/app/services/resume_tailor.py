"""Deterministic resume tailoring from verified facts only."""

from __future__ import annotations

import json
import re

from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import FactType

_TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").casefold()))


def _fact_text(fact: CanonicalFact) -> str:
    return f"{fact.fact_key} {json.dumps(fact.fact_value, ensure_ascii=False)}"


def _score(fact: CanonicalFact, target: set[str]) -> int:
    return len(_tokens(_fact_text(fact)) & target)


def _target_tokens(analysis: dict) -> set[str]:
    blobs = [analysis.get("summary") or ""]
    for group in ("required", "preferred", "technologies", "responsibilities"):
        for item in analysis.get(group) or []:
            blobs.append(item.get("text") or "")
    return _tokens(" ".join(blobs))


def _items(facts: list[CanonicalFact], fact_type: FactType, target: set[str]) -> list[dict]:
    selected = [fact for fact in facts if fact.fact_type is fact_type]
    selected.sort(key=lambda fact: (-_score(fact, target), fact.id))
    return [
        {
            "fact_id": fact.id,
            "title": fact.fact_key,
            "detail": fact.fact_value,
            "relevance": _score(fact, target),
        }
        for fact in selected
    ]


def tailor_resume(candidate: Candidate, facts: list[CanonicalFact], analysis: dict) -> dict:
    target = _target_tokens(analysis)
    return {
        "header": {
            "full_name": candidate.full_name,
            "email": candidate.email,
            "phone": candidate.phone,
            "location": candidate.current_location,
            "school": candidate.school,
            "linkedin_url": candidate.linkedin_url,
            "github_url": candidate.github_url,
        },
        "education": _items(facts, FactType.EDUCATION, target),
        "work_experience": _items(facts, FactType.WORK_EXPERIENCE, target),
        "projects": _items(facts, FactType.PROJECT, target),
        "skills": _items(facts, FactType.SKILL, target),
        "achievements": _items(facts, FactType.ACHIEVEMENT, target),
        "emphasized_terms": sorted(target)[:20],
        "source_fact_ids": [fact.id for fact in facts],
    }


_SKIP_DETAIL_KEYS = {
    "review_reasons",
    "ambiguous_fields",
    "needs_review",
    "unclassified_text",
    "source",
    "fact_id",
}
_SECTION_FIELDS = {
    "education": ("institution", "degree", "major", "location", "dates_text", "gpa", "coursework"),
    "work_experience": ("employer", "position", "location", "dates_text"),
    "projects": ("name", "tagline", "technologies", "dates_text"),
    "skills": ("items",),
    "achievements": ("text", "organization"),
}
_FIELD_LABELS = {
    "institution": "School",
    "degree": "Degree",
    "major": "Major",
    "location": "Location",
    "dates_text": "Dates",
    "gpa": "GPA",
    "coursework": "Coursework",
    "employer": "Employer",
    "position": "Position",
    "name": "Project",
    "tagline": "Subtitle",
    "technologies": "Technologies",
    "items": "Skills",
    "text": "Achievement",
    "organization": "Organization",
}


def _as_text_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def structured_entry_lines(row: dict, section: str) -> list[str]:
    """Readable lines for one resume entry. Never emits serialized JSON."""
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    title = (row.get("title") or "").strip()
    lines: list[str] = []
    heading_parts = []
    if section == "work_experience":
        heading_parts = [detail.get("position"), detail.get("employer")]
    elif section == "projects":
        heading_parts = [detail.get("name") or title]
    elif section == "education":
        heading_parts = [detail.get("institution") or title]
    if any(heading_parts):
        lines.append(" — ".join(part for part in heading_parts if part))
    elif title:
        lines.append(title)
    for key in _SECTION_FIELDS.get(section, ()):
        if key in {"name", "institution", "position", "employer"}:
            continue
        values = _as_text_list(detail.get(key))
        if not values:
            continue
        label = _FIELD_LABELS.get(key, key.replace("_", " ").title())
        if key in {"technologies", "items"}:
            lines.append(f"{label}: {', '.join(values)}")
        else:
            for value in values:
                lines.append(f"{label}: {value}" if key != "text" else value)
    for bullet in _as_text_list(detail.get("bullets")):
        lines.append(f"• {bullet}")
    if not lines and title:
        lines.append(title)
    unused = [
        key
        for key, value in detail.items()
        if key not in _SKIP_DETAIL_KEYS
        and key not in _SECTION_FIELDS.get(section, ())
        and key != "bullets"
        and _as_text_list(value)
    ]
    for key in unused:
        label = _FIELD_LABELS.get(key, key.replace("_", " ").title())
        values = _as_text_list(detail[key])
        if key in {"technologies", "items"}:
            lines.append(f"{label}: {', '.join(values)}")
        else:
            lines.extend(values)
    return [line for line in lines if line and not line.startswith("{")]


def flatten_tailored_lines(document: dict) -> list[str]:
    header = document.get("header") or {}
    lines = [header.get("full_name") or ""]
    contact = " · ".join(part for part in (header.get("email"), header.get("phone"), header.get("location")) if part)
    if contact:
        lines.append(contact)
    for section in ("education", "work_experience", "projects", "skills", "achievements"):
        rows = document.get(section) or []
        if not rows:
            continue
        lines.append(section.replace("_", " ").title())
        for row in rows:
            lines.extend(structured_entry_lines(row, section))
    return [line for line in lines if line]
