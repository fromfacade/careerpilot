"""Deterministic resume tailoring from verified facts only.

Selection and formatting happen only at the presentation layer. Canonical
facts are never deleted, merged, or rewritten here.
"""

from __future__ import annotations

import json
import re

from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import FactType

_TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")
_ORG_STOP_RE = re.compile(r"\b(university of|the|inc|llc|corp|corporation|services|limited|ltd)\b")
_SCHOOL_ALIASES = {
    "ucsc": "uc santa cruz",
    "uc santa cruz": "uc santa cruz",
    "california santa cruz": "uc santa cruz",
}
_INTERNAL_LABEL_RE = re.compile(
    r"^(Dates|Subtitle|Skills|Degree|Major|Location|Technologies|School|"
    r"Employer|Position|Project|Achievement|Organization|Coursework|GPA):",
    re.I,
)
_SKIP_DETAIL_KEYS = {
    "review_reasons",
    "ambiguous_fields",
    "needs_review",
    "unclassified_text",
    "source",
    "fact_id",
}
_SECTION_LIMITS = {
    FactType.EDUCATION: 2,
    FactType.WORK_EXPERIENCE: 3,
    FactType.PROJECT: 3,
    FactType.ACHIEVEMENT: 2,
}
_MAX_PROJECTS = 3
_MIN_PROJECTS = 2
_MAX_BULLETS = 3
_SKILL_ITEM_LIMIT = 8
_SKILL_CATEGORY_ORDER = (
    "Programming Languages",
    "Backend / APIs",
    "Frontend",
    "Databases / Infrastructure",
    "Tools / Platforms",
    "Languages",
)
_SKILL_CATEGORY_ALIASES = {
    "programming languages": "Programming Languages",
    "languages": "Programming Languages",
    "backend": "Backend / APIs",
    "backend / apis": "Backend / APIs",
    "apis": "Backend / APIs",
    "frontend": "Frontend",
    "databases": "Databases / Infrastructure",
    "databases / infrastructure": "Databases / Infrastructure",
    "infrastructure": "Databases / Infrastructure",
    "tools": "Tools / Platforms",
    "tools / platforms": "Tools / Platforms",
    "platforms": "Tools / Platforms",
}
_PROGRAMMING_SKILLS = {
    "python",
    "javascript",
    "typescript",
    "sql",
    "c++",
    "c#",
    "java",
    "go",
    "rust",
    "html",
    "css",
    "r",
}
_SPOKEN_SKILLS = {"english", "spanish", "french", "mandarin", "german", "portuguese", "italian", "japanese", "korean"}
_SECTION_TITLES = {
    "education": "EDUCATION",
    "work_experience": "EXPERIENCE",
    "projects": "PROJECTS",
    "skills": "SKILLS",
    "achievements": "ACHIEVEMENTS",
}
_UNICODE_ASCII = {
    "\u2022": "-",
    "\u2014": "-",
    "\u2013": "-",
    "\u00b7": "|",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00a0": " ",
}


def ascii_safe(text: str) -> str:
    """Map common resume punctuation to Helvetica-safe ASCII."""
    value = text or ""
    for source, dest in _UNICODE_ASCII.items():
        value = value.replace(source, dest)
    return value


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").casefold()))


def _norm(text: str) -> str:
    value = ascii_safe(text or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9+#./]+", " ", value)
    return " ".join(value.split())


def _norm_org(text: str) -> str:
    value = _ORG_STOP_RE.sub(" ", _norm(text))
    value = " ".join(value.split())
    return _SCHOOL_ALIASES.get(value, value)


def _similar_name(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return min(len(left.split()), len(right.split())) >= 2 or min(len(left), len(right)) >= 8
    shared = set(left.split()) & set(right.split())
    union = set(left.split()) | set(right.split())
    return len(shared) >= 2 and len(shared) / len(union) >= 0.6


def _fact_text(fact: CanonicalFact) -> str:
    return f"{fact.fact_key} {json.dumps(fact.fact_value, ensure_ascii=False)}"


def _score(fact: CanonicalFact, target: set[str]) -> int:
    if fact.fact_type is FactType.PROJECT:
        return _project_score(fact, target)
    return len(_tokens(_fact_text(fact)) & target)


_GENERIC_TECH = {
    "postgresql",
    "docker",
    "sql",
    "git",
    "github",
    "linux",
    "unix",
    "rest",
    "apis",
    "api",
    "json",
}
_JD_STOP = {
    "software",
    "engineering",
    "engineer",
    "intern",
    "internship",
    "role",
    "team",
    "using",
    "build",
    "building",
    "built",
    "services",
    "service",
    "data",
    "stores",
    "required",
    "preferred",
    "experience",
    "work",
    "working",
    "with",
    "full",
    "stack",
    "product",
    "features",
    "user",
    "interfaces",
    "reliable",
    "workflows",
    "language",
    "models",
    "machine",
    "learning",
    "background",
    "job",
    "processing",
    "and",
    "the",
    "for",
    "this",
    "systems",
    "applied",
}


def _project_score(fact: CanonicalFact, target: set[str]) -> int:
    detail = _detail(fact)
    tech = _tokens(" ".join(_as_text_list(detail.get("technologies"))))
    name = _tokens(str(detail.get("name") or fact.fact_key))
    bullets = _tokens(" ".join(_as_text_list(detail.get("bullets"))))
    matched_tech = tech & target
    specific = matched_tech - _GENERIC_TECH
    generic = matched_tech & _GENERIC_TECH
    return (
        4 * len(specific)
        + len(generic)
        + 2 * len((name & target) - _JD_STOP)
        + len((bullets & target) - _GENERIC_TECH - _JD_STOP)
    )


def _matched_terms(fact: CanonicalFact, target: set[str]) -> list[str]:
    detail = _detail(fact)
    haystack = _tokens(
        " ".join(
            [
                str(detail.get("name") or fact.fact_key),
                " ".join(_as_text_list(detail.get("technologies"))),
                " ".join(_as_text_list(detail.get("bullets"))),
            ]
        )
    )
    return sorted(haystack & target)


def _selection_reason(fact: CanonicalFact, target: set[str]) -> str:
    matched = _matched_terms(fact, target)[:5]
    if matched:
        return "Matches this role's " + ", ".join(matched) + "."
    return "Included as additional verified experience."


def _copy_detail(fact: CanonicalFact, target: set[str]) -> dict:
    raw = _detail(fact)
    detail = dict(raw)
    bullets = _as_text_list(raw.get("bullets"))
    if bullets:
        ranked = sorted(range(len(bullets)), key=lambda index: (-len(_tokens(bullets[index]) & target), index))
        detail["included_bullet_indexes"] = sorted(ranked[:_MAX_BULLETS])
        detail["bullets"] = bullets
    return detail


def _target_tokens(analysis: dict) -> set[str]:
    blobs = [analysis.get("summary") or ""]
    for group in ("required", "preferred", "technologies", "responsibilities"):
        for item in analysis.get(group) or []:
            blobs.append(item.get("text") or "")
    return _tokens(" ".join(blobs))


def _detail(fact: CanonicalFact) -> dict:
    return fact.fact_value if isinstance(fact.fact_value, dict) else {}


def _as_text_list(value) -> list[str]:
    if isinstance(value, list):
        return [ascii_safe(str(item)).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [ascii_safe(value).strip()]
    return []


def _completeness(fact: CanonicalFact) -> int:
    total = 0
    for key, value in _detail(fact).items():
        if key in _SKIP_DETAIL_KEYS:
            continue
        total += len(_as_text_list(value))
    return total


def _identity_key(fact: CanonicalFact) -> str:
    explicit = getattr(fact, "identity_key", None)
    if explicit:
        return str(explicit)
    return f"{fact.fact_type.value}|{_norm(fact.fact_key)}"


def _cluster_key(fact: CanonicalFact) -> str:
    """Semantic display identity. Different identity_keys can still collide."""
    detail = _detail(fact)
    if fact.fact_type is FactType.EDUCATION:
        school = _norm_org(detail.get("institution") or detail.get("school") or fact.fact_key)
        degree = _norm(str(detail.get("degree") or ""))
        return f"education|{school}|{degree}"
    if fact.fact_type is FactType.WORK_EXPERIENCE:
        employer = _norm_org(detail.get("employer") or fact.fact_key)
        position = _norm(str(detail.get("position") or fact.fact_key))
        return f"work|{employer}|{position}"
    if fact.fact_type is FactType.PROJECT:
        name = _norm(str(detail.get("name") or fact.fact_key))
        return f"project|{name}"
    if fact.fact_type is FactType.ACHIEVEMENT:
        text = _norm(str(detail.get("text") or fact.fact_key))[:80]
        return f"achievement|{text}"
    if fact.fact_type is FactType.SKILL:
        return f"skill|{_norm(fact.fact_key)}"
    return _identity_key(fact)


def _same_cluster(left: CanonicalFact, right: CanonicalFact) -> bool:
    if left.fact_type is not right.fact_type:
        return False
    if _identity_key(left) == _identity_key(right):
        return True
    if left.fact_type is FactType.EDUCATION:
        left_school = _norm_org(_detail(left).get("institution") or _detail(left).get("school") or left.fact_key)
        right_school = _norm_org(_detail(right).get("institution") or _detail(right).get("school") or right.fact_key)
        left_degree = _norm(str(_detail(left).get("degree") or ""))
        right_degree = _norm(str(_detail(right).get("degree") or ""))
        if left_school != right_school:
            return False
        return not left_degree or not right_degree or left_degree == right_degree
    if left.fact_type is FactType.WORK_EXPERIENCE:
        left_emp = _norm_org(_detail(left).get("employer") or left.fact_key)
        right_emp = _norm_org(_detail(right).get("employer") or right.fact_key)
        left_pos = _norm(str(_detail(left).get("position") or left.fact_key))
        right_pos = _norm(str(_detail(right).get("position") or right.fact_key))
        return left_emp == right_emp and _similar_name(left_pos, right_pos)
    if left.fact_type is FactType.PROJECT:
        return _similar_name(
            _norm(str(_detail(left).get("name") or left.fact_key)),
            _norm(str(_detail(right).get("name") or right.fact_key)),
        )
    if left.fact_type is FactType.ACHIEVEMENT:
        return _cluster_key(left) == _cluster_key(right)
    return _cluster_key(left) == _cluster_key(right)


def _pick_representative(group: list[CanonicalFact], target: set[str]) -> CanonicalFact:
    return max(group, key=lambda fact: (_score(fact, target), _completeness(fact), -fact.id))


def _cluster_facts(facts: list[CanonicalFact], target: set[str]) -> list[tuple[CanonicalFact, list[int]]]:
    clusters: list[list[CanonicalFact]] = []
    for fact in facts:
        placed = False
        for group in clusters:
            if _same_cluster(group[0], fact):
                group.append(fact)
                placed = True
                break
        if not placed:
            clusters.append([fact])
    ranked = []
    for group in clusters:
        winner = _pick_representative(group, target)
        ranked.append((winner, [item.id for item in group]))
    ranked.sort(key=lambda pair: (-_score(pair[0], target), -_completeness(pair[0]), pair[0].id))
    return ranked


def _row(fact: CanonicalFact, target: set[str], *, included: bool, source_ids: list[int]) -> dict:
    return {
        "fact_id": fact.id,
        "title": fact.fact_key,
        "detail": _copy_detail(fact, target),
        "relevance": _score(fact, target),
        "included": included,
        "identity_key": _identity_key(fact),
        "source_fact_ids": source_ids,
        "selection_reason": _selection_reason(fact, target) if included else "",
    }


def _visible_entry_rows(facts: list[CanonicalFact], fact_type: FactType, target: set[str]) -> list[dict]:
    selected = [fact for fact in facts if fact.fact_type is fact_type]
    clusters = _cluster_facts(selected, target)
    if fact_type is FactType.PROJECT:
        return _project_rows(clusters, target)
    limit = _SECTION_LIMITS.get(fact_type)
    rows = []
    for index, (fact, source_ids) in enumerate(clusters):
        included = limit is None or index < limit
        rows.append(_row(fact, target, included=included, source_ids=source_ids))
    return rows


def _project_rows(clusters: list[tuple[CanonicalFact, list[int]]], target: set[str]) -> list[dict]:
    rows = [_row(fact, target, included=False, source_ids=source_ids) for fact, source_ids in clusters]
    strong = [row for row in rows if (row["relevance"] or 0) >= 4]
    chosen = strong[:_MAX_PROJECTS]
    if len(chosen) < _MIN_PROJECTS:
        extras = [row for row in rows if row not in chosen]
        chosen.extend(extras[: _MIN_PROJECTS - len(chosen)])
    chosen_ids = {row["fact_id"] for row in chosen}
    for row in rows:
        row["included"] = row["fact_id"] in chosen_ids
        row["selection_reason"] = _project_reason(row) if row["included"] else ""
    return rows


def _project_reason(row: dict) -> str:
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    matched = []
    target_hint = row.get("selection_reason") or ""
    if row.get("relevance"):
        tech = ", ".join(_as_text_list(detail.get("technologies"))[:4])
        if tech:
            return f"Relevant technical experience ({tech})."
    return target_hint or "Included as additional verified project experience."


def _skill_category(fact: CanonicalFact) -> str:
    key = _norm(fact.fact_key)
    items = {_norm(item) for item in _as_text_list(_detail(fact).get("items"))}
    if items and items <= _SPOKEN_SKILLS:
        return "Languages"
    if key in _SKILL_CATEGORY_ALIASES:
        if key == "languages" and items and items <= _PROGRAMMING_SKILLS:
            return "Programming Languages"
        if key == "languages" and items and items <= _SPOKEN_SKILLS:
            return "Languages"
        if key == "languages" and items & _PROGRAMMING_SKILLS:
            return "Programming Languages"
        return _SKILL_CATEGORY_ALIASES[key]
    return fact.fact_key.strip() or "Skills"


def _skill_rows(facts: list[CanonicalFact], target: set[str]) -> list[dict]:
    groups = [fact for fact in facts if fact.fact_type is FactType.SKILL]
    if not groups:
        return []
    seen: set[str] = set()
    buckets: dict[str, list[tuple[int, str]]] = {name: [] for name in _SKILL_CATEGORY_ORDER}
    extra_order: list[str] = []
    source_by_category: dict[str, list[int]] = {}
    for fact in groups:
        category = _skill_category(fact)
        source_by_category.setdefault(category, []).append(fact.id)
        if category not in buckets:
            buckets[category] = []
            extra_order.append(category)
        for item in _as_text_list(_detail(fact).get("items")):
            key = _norm(item)
            if not key or key in seen:
                continue
            seen.add(key)
            buckets[category].append((len(_tokens(item) & target), item))
    rows = []
    for category in list(_SKILL_CATEGORY_ORDER) + extra_order:
        ranked = sorted(buckets.get(category) or [], key=lambda pair: (-pair[0], pair[1].casefold()))
        items = [item for _, item in ranked[:_SKILL_ITEM_LIMIT]]
        if not items:
            continue
        rows.append(
            {
                "fact_id": (source_by_category.get(category) or [groups[0].id])[0],
                "title": category,
                "detail": {"category": category, "items": items},
                "relevance": max((score for score, _ in ranked), default=0),
                "included": True,
                "identity_key": f"skill|{_norm(category)}",
                "source_fact_ids": source_by_category.get(category) or [groups[0].id],
                "selection_reason": "",
            }
        )
    return rows


def _bullet_blob(rows: list[dict]) -> str:
    parts = []
    for row in rows:
        if row.get("included") is False:
            continue
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        parts.extend(_as_text_list(detail.get("bullets")))
        parts.extend(_as_text_list(detail.get("text")))
    return " ".join(_norm(part) for part in parts)


def _achievement_already_covered(row: dict, covered: str) -> bool:
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    text = _norm(" ".join(_as_text_list(detail.get("text")) or [row.get("title") or ""]))
    return bool(text) and len(text) >= 24 and text in covered


def tailor_resume(candidate: Candidate, facts: list[CanonicalFact], analysis: dict) -> dict:
    target = _target_tokens(analysis)
    education = _visible_entry_rows(facts, FactType.EDUCATION, target)
    work = _visible_entry_rows(facts, FactType.WORK_EXPERIENCE, target)
    projects = _visible_entry_rows(facts, FactType.PROJECT, target)
    covered = _bullet_blob(work + projects)
    achievements = []
    for row in _visible_entry_rows(facts, FactType.ACHIEVEMENT, target):
        if _achievement_already_covered(row, covered):
            row = {**row, "included": False}
        achievements.append(row)
    omitted = [
        row["fact_id"]
        for section in (education, work, projects, achievements)
        for row in section
        if row.get("included") is False
    ]
    return {
        "header": {
            "full_name": candidate.full_name,
            "email": candidate.email,
            "phone": candidate.phone,
            "location": candidate.current_location,
            "school": candidate.school,
            "linkedin_url": candidate.linkedin_url,
            "github_url": candidate.github_url,
            "portfolio_url": getattr(candidate, "portfolio_url", None),
        },
        "education": education,
        "work_experience": work,
        "projects": projects,
        "skills": _skill_rows(facts, target),
        "achievements": achievements,
        "emphasized_terms": sorted(target)[:20],
        "source_fact_ids": [fact.id for fact in facts],
        "presentation": {
            "omitted_fact_ids": omitted,
            "page_budget": "auto",
            "note": (
                "Duplicate or lower-priority entries are hidden in the export only. "
                "Canonical facts were not changed. Include a hidden row before approval "
                "if it should appear."
            ),
        },
    }


def _contact_line(header: dict) -> str:
    parts = [
        header.get("email"),
        header.get("phone"),
        header.get("location"),
        header.get("linkedin_url"),
        header.get("github_url"),
        header.get("portfolio_url"),
    ]
    return " | ".join(ascii_safe(part) for part in parts if part)


def _heading_for(section: str, title: str, detail: dict) -> str:
    if section == "work_experience":
        parts = [detail.get("position"), detail.get("employer")]
        return " - ".join(ascii_safe(part) for part in parts if part) or ascii_safe(title)
    if section == "projects":
        name = ascii_safe(str(detail.get("name") or title))
        tagline = ascii_safe(str(detail.get("tagline") or "")).strip()
        return f"{name} - {tagline}" if tagline else name
    if section == "education":
        return ascii_safe(str(detail.get("institution") or detail.get("school") or title))
    if section == "skills":
        return ""
    if section == "achievements":
        organization = ascii_safe(str(detail.get("organization") or "")).strip()
        if organization:
            return organization
        text = ascii_safe(str(detail.get("text") or "")).strip()
        if title and title != text and len(title.split()) <= 8:
            return ascii_safe(title)
        return ""
    return ascii_safe(title)


def _meta_for(section: str, detail: dict) -> str:
    if section == "education":
        parts = [
            *_as_text_list(detail.get("degree")),
            *_as_text_list(detail.get("major")),
            *_as_text_list(detail.get("location")),
            *_as_text_list(detail.get("dates_text")),
        ]
        gpa = _as_text_list(detail.get("gpa"))
        if gpa:
            parts.append(f"GPA {gpa[0]}")
        line = " | ".join(parts)
        coursework = _as_text_list(detail.get("coursework"))
        if coursework:
            extra = ", ".join(coursework)
            return f"{line}\n{extra}" if line else extra
        return line
    if section == "work_experience":
        return " | ".join(
            [
                *_as_text_list(detail.get("location")),
                *_as_text_list(detail.get("dates_text")),
            ]
        )
    if section == "projects":
        tech = ", ".join(_as_text_list(detail.get("technologies")))
        dates = " | ".join(_as_text_list(detail.get("dates_text")))
        return " | ".join(part for part in (tech, dates) if part)
    if section == "skills":
        items = ", ".join(_as_text_list(detail.get("items")))
        category = ascii_safe(str(detail.get("category") or "")).strip()
        if category and items:
            return f"{category}: {items}"
        return items
    return ""


def structured_entry_lines(row: dict, section: str) -> list[str]:
    """Resume-style lines for one entry. Never emits labels or serialized JSON."""
    if row.get("included") is False:
        return []
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    title = ascii_safe((row.get("title") or "").strip())
    heading = _heading_for(section, title, detail)
    meta = _meta_for(section, detail)
    lines: list[str] = []
    if heading:
        lines.append(heading)
    if meta:
        lines.extend(part for part in meta.split("\n") if part)
    bullets = _as_text_list(detail.get("bullets"))
    included_indexes = detail.get("included_bullet_indexes")
    if isinstance(included_indexes, list) and bullets:
        chosen = [bullets[index] for index in included_indexes if isinstance(index, int) and 0 <= index < len(bullets)]
    else:
        chosen = bullets
    for bullet in chosen:
        lines.append(f"- {bullet}")
    if section == "achievements":
        for value in _as_text_list(detail.get("text")):
            if value and all(value not in line for line in lines):
                lines.append(f"- {value}")
    cleaned = [line for line in lines if line and not line.startswith("{") and not _INTERNAL_LABEL_RE.match(line)]
    if not cleaned and title:
        return [title]
    return cleaned


def iter_resume_lines(document: dict) -> list[tuple[str, str]]:
    """Typed resume lines for consistent PDF/DOCX typography."""
    header = document.get("header") or {}
    rows_out: list[tuple[str, str]] = []
    name = ascii_safe(header.get("full_name") or "")
    if name:
        rows_out.append(("name", name))
    contact = _contact_line(header)
    if contact:
        rows_out.append(("contact", contact))
    for section, heading in _SECTION_TITLES.items():
        visible = [row for row in (document.get(section) or []) if row.get("included") is not False]
        entries = [(row, structured_entry_lines(row, section)) for row in visible]
        entries = [(row, lines) for row, lines in entries if lines]
        if not entries:
            continue
        rows_out.append(("section", heading))
        for _row, lines in entries:
            if section == "skills":
                rows_out.extend(("meta", line) for line in lines)
                continue
            if lines[0].startswith("- "):
                rows_out.extend(("bullet", line) for line in lines)
                continue
            rows_out.append(("heading", lines[0]))
            for line in lines[1:]:
                rows_out.append(("bullet", line) if line.startswith("- ") else ("meta", line))
    return rows_out


def flatten_tailored_lines(document: dict) -> list[str]:
    return [text for _kind, text in iter_resume_lines(document)]


def visible_rows(document: dict, section: str) -> list[dict]:
    return [row for row in (document.get(section) or []) if row.get("included") is not False]


def assess_resume_quality(
    document: dict,
    *,
    extracted: str | None = None,
    page_count: int | None = None,
    empty_pages: int = 0,
) -> dict:
    """Presentation checks only. Does not mutate canonical facts."""
    issues: list[str] = []
    warnings: list[str] = []
    lines = flatten_tailored_lines(document)
    header = document.get("header") or {}
    if not (header.get("full_name") or "").strip():
        issues.append("Missing candidate name.")
    if not any(header.get(key) for key in ("email", "phone", "location", "linkedin_url", "github_url")):
        issues.append("Contact information is missing.")
    required_present = any(visible_rows(document, section) for section in ("education", "work_experience", "projects"))
    if not required_present:
        issues.append("Resume is missing education, experience, and projects.")
    labeled = [line for line in lines if _INTERNAL_LABEL_RE.match(line.strip())]
    if labeled:
        issues.append("Internal field labels are visible: " + "; ".join(labeled[:3]))
    skill_lines = [line for kind, line in iter_resume_lines(document) if kind == "meta" and ": " in line]
    skill_rows = visible_rows(document, "skills")
    if len(skill_rows) >= 2 and not any(row.get("detail", {}).get("category") for row in skill_rows if isinstance(row.get("detail"), dict)):
        issues.append("Technical skills are not grouped into categories.")
    if skill_rows and not any(any(name in line for name in _SKILL_CATEGORY_ORDER) for line in skill_lines + [str(row.get("title") or "") for row in skill_rows]):
        warnings.append("Skills are present but no standard category labels were found.")
    for row in visible_rows(document, "achievements"):
        entry = structured_entry_lines(row, "achievements")
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        text = " ".join(_as_text_list(detail.get("text")))
        if entry and text and _norm(entry[0]) == _norm(text):
            issues.append("Achievement description is used as a heading.")
        blob = " ".join(entry)
        if text and blob.count(text) > 1:
            issues.append("An achievement description is repeated.")
    headings: list[str] = []
    bullets: list[str] = []
    for section in _SECTION_TITLES:
        for row in visible_rows(document, section):
            entry = structured_entry_lines(row, section)
            if entry:
                headings.append(_norm(entry[0]))
            bullets.extend(_norm(line[2:]) for line in entry if line.startswith("- "))
    duplicates = sorted({item for item in headings if item and headings.count(item) > 1})
    if duplicates:
        issues.append("Duplicate entries: " + "; ".join(duplicates[:4]))
    repeated_bullets = sorted({item for item in bullets if item and bullets.count(item) > 1})
    if repeated_bullets:
        issues.append("Duplicate accomplishments: " + "; ".join(repeated_bullets[:3]))
    if empty_pages:
        issues.append(f"Export produced {empty_pages} blank page(s).")
    if extracted is not None:
        if len(extracted.strip()) < 40:
            issues.append("PDF text extraction did not return readable resume text.")
        if re.search(r"(^|\n)\?\s", extracted):
            issues.append("PDF used replacement characters for bullets or separators.")
        if any(_INTERNAL_LABEL_RE.match(line.strip()) for line in extracted.splitlines()):
            issues.append("Internal field labels are visible in the exported file.")
        if any(marker in extracted for marker in ("review_reasons", "'name':", '"ambiguous_fields"')):
            issues.append("Export contained parser metadata instead of formatted text.")
    if page_count is not None and page_count > 2:
        issues.append(f"Resume is {page_count} pages; internship applications should stay near one page.")
    elif page_count is not None and page_count > 1:
        warnings.append("Resume is longer than one page. Hide lower-priority rows if you want a one-page version.")
    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "page_count": page_count,
        "line_count": len(lines),
    }


def _trim_extra_bullets(row: dict) -> bool:
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    indexes = list(detail.get("included_bullet_indexes") or [])
    bullets = _as_text_list(detail.get("bullets"))
    if len(indexes) > 2:
        detail["included_bullet_indexes"] = indexes[:2]
        row["detail"] = detail
        return True
    if not indexes and len(bullets) > 2:
        detail["included_bullet_indexes"] = list(range(2))
        row["detail"] = detail
        return True
    return False


def hide_lowest_priority_content(document: dict) -> bool:
    """Hide one presentation-only item so a one-page export can fit. Facts stay intact."""
    projects = [row for row in (document.get("projects") or []) if row.get("included") is not False]
    if len(projects) > _MIN_PROJECTS:
        weakest = min(projects, key=lambda row: (row.get("relevance") or 0, -(row.get("fact_id") or 0)))
        weakest["included"] = False
        weakest["selection_reason"] = ""
        return True
    achievements = [row for row in (document.get("achievements") or []) if row.get("included") is not False]
    if achievements:
        achievements[-1]["included"] = False
        return True
    for section in ("projects", "work_experience"):
        for row in document.get(section) or []:
            if row.get("included") is False:
                continue
            if _trim_extra_bullets(row):
                return True
    return False


def ranked_project_rows(document: dict) -> list[dict]:
    return sorted(
        document.get("projects") or [],
        key=lambda row: (-(row.get("relevance") or 0), row.get("fact_id") or 0),
    )
