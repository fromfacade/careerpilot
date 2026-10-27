"""Deterministic, rule-based resume section parsing.

No AI, no network calls, no guessing of facts not present in the text.
Dates are kept as whatever substring was actually matched in the resume --
never parsed/rounded into a specific `date` value, since that would risk
asserting a precision the source text doesn't actually have.

The document is cut into sections at *section headings* only (a heading
stands alone on its line: `EDUCATION`, `TECHNICAL SKILLS :`, `PROJECTS`).
Everything below a heading belongs to that section until the next heading,
so a labeled line such as `Technologies: Python, Go` inside a project can
never open a Skills section. Work experience and projects are parsed by
`entry_parser`; skills only ever come from a skills section.

If section headers can't be confidently found, the whole document (or
whatever part of it couldn't be segmented) becomes a single `FactType.OTHER`
fact rather than being dropped or fabricated into a false structure. This
mirrors the project's existing "surface `unknown`, never silently assume"
rule used for eligibility/relevance (see docs/architecture.md §6a).

Every `ExtractedFact.raw_text` is the verbatim source substring it came
from, so a human reviewer (via `PATCH /api/candidate/facts/{id}`) can check
the extraction against the original wording before marking it verified.
"""

from __future__ import annotations

import re

from app.models.enums import FactType
from app.resume_parsing.entry_parser import looks_like_prose, parse_project_section, parse_work_section
from app.resume_parsing.skill_items import (
    NOISE_KEYS,
    is_noise_line,
    item_looks_like_skill,
    looks_like_tech_list,
    split_skill_items,
)
from app.resume_parsing.text_normalize import (
    DATE_RANGE_RE,
    DATE_TOKEN,
    LOCATION_RE,
    is_bullet_line,
    looks_like_job_header,
    looks_like_project_title,
    looks_like_sentence_fragment,
    match_section_header,
    normalize_extracted_text,
    strip_bullet,
)
from app.resume_parsing.types import ExtractedFact, review_fields

__all__ = ["ExtractedFact", "parse_resume_text"]

_MAX_SKILL_CATEGORY_LEN = 35

_EXPECTED_GRAD_RE = re.compile(
    r"(?:expected\s+)?(?:graduation|graduating)\s*:?\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})",
    re.IGNORECASE,
)
_GPA_RE = re.compile(r"\bGPA\s*:?\s*([0-4](?:\.\d+)?(?:\s*/\s*[0-4](?:\.\d+)?)?)", re.IGNORECASE)
_DEGREE_RE = re.compile(
    r"\b("
    r"A\.?A\.?|A\.?S\.?|A\.?A\.?S\.?|"
    r"B\.?A\.?|B\.?S\.?|B\.?Sc\.?|B\.?E\.?|B\.?Eng\.?|"
    r"M\.?A\.?|M\.?S\.?|M\.?Sc\.?|M\.?Eng\.?|MBA|M\.?B\.?A\.?|"
    r"Ph\.?D\.?|J\.?D\.?|"
    r"Bachelor(?:'s)?(?:\s+of\s+[A-Za-z]+)?|"
    r"Master(?:'s)?(?:\s+of\s+[A-Za-z]+)?|"
    r"Associate(?:'s)?(?:\s+of\s+[A-Za-z]+)?|"
    r"Doctorate"
    r")\b\.?",
    re.IGNORECASE,
)
_MAJOR_AFTER_DEGREE_RE = re.compile(
    r"(?:bachelor(?:'s)?|master(?:'s)?|associate(?:'s)?|b\.?s\.?|b\.?a\.?|m\.?s\.?|m\.?a\.?|ph\.?d\.?)"
    r"\s*(?:,|in|-|—|–)?\s+([A-Za-z][A-Za-z0-9 /&+.-]{2,80})",
    re.IGNORECASE,
)
_INSTITUTION_RE = re.compile(
    r"\b(university|college|institute|academy|school|polytechnic)\b",
    re.IGNORECASE,
)
_SEGMENT_SPLIT_RE = re.compile(r"\s*\|\s*|\s+[—–-]\s+")


def parse_resume_text(text: str) -> list[ExtractedFact]:
    """Segment raw resume text into `ExtractedFact` objects.

    Always returns at least one fact for any non-empty input: if section
    headers can't be found (or every detected section turns out empty),
    the fallback is a single `FactType.OTHER` fact holding the full text,
    never an empty list and never a fabricated structure.
    """
    text = normalize_extracted_text(text)
    if not text:
        return []

    lines = text.splitlines()
    headers = _find_headers(lines)
    if not headers:
        return [_fallback_fact(text)]

    facts: list[ExtractedFact] = []
    for idx, (line_no, fact_type, inline_remainder) in enumerate(headers):
        start = line_no + 1
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        section_lines = list(lines[start:end])
        if inline_remainder:
            section_lines = [inline_remainder, *section_lines]

        if fact_type == FactType.SKILL:
            facts.extend(_parse_skills_section(section_lines))
        elif fact_type == FactType.ACHIEVEMENT:
            facts.extend(_parse_achievement_section(section_lines))
        elif fact_type == FactType.EDUCATION:
            facts.extend(_parse_education_section(section_lines))
        elif fact_type == FactType.WORK_EXPERIENCE:
            facts.extend(parse_work_section(section_lines))
        elif fact_type == FactType.PROJECT:
            facts.extend(parse_project_section(section_lines))
        else:
            facts.extend(_parse_blocked_section(section_lines, fact_type))

    if not facts:
        return [_fallback_fact(text)]
    return facts


def _fallback_fact(text: str) -> ExtractedFact:
    return ExtractedFact(
        fact_type=FactType.OTHER,
        fact_key="Unstructured resume text",
        fact_value={"text": text},
        raw_text=text,
    )


def _find_headers(lines: list[str]) -> list[tuple[int, FactType, str | None]]:
    """Return `(line_index, fact_type, inline_remainder_after_colon)` for
    every line recognized as a section heading, in document order."""
    found: list[tuple[int, FactType, str | None]] = []
    for i, line in enumerate(lines):
        matched = match_section_header(line)
        if matched is not None:
            found.append((i, matched[0], matched[1]))
    return found


_is_bullet_line = is_bullet_line
_strip_bullet = strip_bullet
_is_noise_line = is_noise_line
_DATE_RANGE = DATE_RANGE_RE


def _is_date_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if DATE_RANGE_RE.search(stripped):
        return True
    if _EXPECTED_GRAD_RE.search(stripped):
        return True
    return bool(re.fullmatch(DATE_TOKEN, stripped, flags=re.IGNORECASE))


def _looks_like_institution(line: str) -> bool:
    return bool(_INSTITUTION_RE.search(line))


def _first_date_text(text: str) -> str | None:
    expected = _EXPECTED_GRAD_RE.search(text)
    if expected:
        return expected.group(0)
    matched = DATE_RANGE_RE.search(text)
    return matched.group(0) if matched else None


def _split_into_blocks(lines: list[str]) -> list[list[str]]:
    """Split a section into per-entry blocks (education / generic sections).

    A new block starts only on a blank line *or* when a bullet-run ends
    and the next line looks like a new heading -- never because a single
    leftover word landed on its own line. If neither signal finds more
    than one block, the whole section stays one block so we never invent
    structure the source text does not have.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
            continue
        if is_noise_line(line) and not current:
            continue
        current.append(line)
    if current:
        blocks.append(current)

    if len(blocks) > 1:
        return _merge_continuation_blocks(blocks)
    if len(blocks) == 1:
        secondary = _split_single_block_heuristically(blocks[0])
        if len(secondary) > 1:
            return secondary
    return blocks


def _merge_continuation_blocks(blocks: list[list[str]]) -> list[list[str]]:
    """Re-attach blocks that are clearly leftovers of the previous entry
    (a date line, a GPA line, or a short continuation) rather than a new
    school / entry."""
    merged: list[list[str]] = []
    for block in blocks:
        if not merged:
            merged.append(list(block))
            continue
        first = next((line for line in block if line.strip()), "")
        if _is_continuation_start(first) and not _looks_like_new_record_start(first):
            merged[-1].extend(block)
        else:
            merged.append(list(block))
    return merged


def _is_continuation_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if is_bullet_line(stripped) or _is_date_line(stripped) or _GPA_RE.search(stripped):
        return True
    if stripped.lower().startswith(("gpa", "relevant coursework", "coursework", "minor")):
        return True
    if looks_like_sentence_fragment(stripped) and not is_bullet_line(stripped):
        return True
    return False


def _looks_like_new_record_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped or is_bullet_line(stripped) or _is_date_line(stripped):
        return False
    if _looks_like_institution(stripped):
        return True
    if looks_like_project_title(stripped) or looks_like_job_header(stripped):
        return True
    return False


def _looks_like_tech_list(text: str) -> bool:
    return looks_like_tech_list(text)


def _split_single_block_heuristically(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    prev_was_bullet = False
    for line in lines:
        if line.strip() == "":
            continue
        starts_new_entry = (
            prev_was_bullet
            and not is_bullet_line(line)
            and not _is_date_line(line)
            and not is_noise_line(line)
            and not _GPA_RE.search(line)
            and not looks_like_sentence_fragment(line)
            and not _looks_like_tech_list(line)
        )
        if starts_new_entry and current:
            blocks.append(current)
            current = []
        current.append(line)
        prev_was_bullet = is_bullet_line(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_blocked_section(lines: list[str], fact_type: FactType) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for block in _split_into_blocks(lines):
        fact = _fact_from_generic_block(block, fact_type)
        if fact is not None:
            facts.append(fact)
    return facts


def _fact_from_generic_block(block: list[str], fact_type: FactType) -> ExtractedFact | None:
    non_empty = [line.strip() for line in block if line.strip() and not is_noise_line(line)]
    if not non_empty:
        return None

    block_text = "\n".join(line.strip() for line in block if line.strip())
    bullets = [strip_bullet(line) for line in block if is_bullet_line(line)]
    return ExtractedFact(
        fact_type=fact_type,
        fact_key=non_empty[0][:150],
        fact_value={
            "raw_block": block_text,
            "bullets": bullets,
            "dates_text": _first_date_text(block_text),
        },
        raw_text=block_text,
    )


def _parse_education_section(lines: list[str]) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for block in _split_education_blocks(lines):
        fact = _structure_education_block(block)
        if fact is not None:
            facts.append(fact)
    return facts


def _split_education_blocks(lines: list[str]) -> list[list[str]]:
    """Prefer one block per school. A new institution name after we already
    have one starts a new record; GPA / coursework / dates stay with the
    current school."""
    blocks = _split_into_blocks(lines)
    if len(blocks) > 1:
        return blocks

    if not blocks:
        return []

    refined: list[list[str]] = []
    current: list[str] = []
    saw_institution = False
    for line in blocks[0]:
        if saw_institution and _looks_like_institution(line) and current and not _is_coursework_line(line):
            refined.append(current)
            current = [line]
            continue
        current.append(line)
        if _looks_like_institution(line):
            saw_institution = True
    if current:
        refined.append(current)
    return refined or blocks


def _is_coursework_line(line: str) -> bool:
    return line.strip().lower().startswith(("relevant coursework", "coursework"))


def _institution_and_location(line: str) -> tuple[str, str | None]:
    segments = [s.strip(" ,;:|") for s in _SEGMENT_SPLIT_RE.split(line)]
    segments = [s for s in segments if s]
    institution = next((s for s in segments if _looks_like_institution(s)), None)
    location = next((s for s in segments if LOCATION_RE.fullmatch(s)), None)
    return (institution or line.strip()), location


def _structure_education_block(block: list[str]) -> ExtractedFact | None:
    non_empty = [line.strip() for line in block if line.strip()]
    if not non_empty:
        return None
    block_text = "\n".join(non_empty)
    if is_noise_line(non_empty[0]) and len(non_empty) == 1:
        return None

    institution_line = next(
        (line for line in non_empty if _looks_like_institution(line) and not _is_coursework_line(line)),
        None,
    )
    institution: str | None = None
    location: str | None = None
    if institution_line is not None:
        institution, location = _institution_and_location(institution_line)

    degree_match = _DEGREE_RE.search(block_text)
    degree = degree_match.group(0).strip(" ,;-") if degree_match else None
    major = None
    major_match = _MAJOR_AFTER_DEGREE_RE.search(block_text)
    if major_match:
        major = major_match.group(1).strip(" ,;-")
        major = re.split(r"\b(?:expected|graduation|gpa|relevant)\b", major, maxsplit=1, flags=re.IGNORECASE)[0]
        major = major.strip(" ,;-")
        if len(major) < 2:
            major = None
    gpa_match = _GPA_RE.search(block_text)
    gpa = gpa_match.group(1).strip() if gpa_match else None
    dates_text = _first_date_text(block_text)
    bullets = [strip_bullet(line) for line in non_empty if is_bullet_line(line)]
    coursework = next(
        (line.split(":", 1)[1].strip() for line in non_empty if line.lower().startswith("relevant coursework")),
        None,
    )

    key = institution or (non_empty[0][:150] if not is_noise_line(non_empty[0]) else "Education")
    return ExtractedFact(
        fact_type=FactType.EDUCATION,
        fact_key=key[:150],
        fact_value={
            "institution": institution,
            "location": location,
            "degree": degree,
            "major": major,
            "gpa": gpa,
            "dates_text": dates_text,
            "coursework": coursework,
            "bullets": bullets,
            "raw_block": block_text,
        },
        raw_text=block_text,
    )


def _skills_review_fact(content: str, raw: str, reason: str) -> ExtractedFact:
    return ExtractedFact(
        fact_type=FactType.OTHER,
        fact_key="Unrecognized line in skills section",
        fact_value={"text": content, **review_fields([reason], [])},
        raw_text=raw,
    )


def _parse_skills_section(lines: list[str]) -> list[ExtractedFact]:
    """One fact per *category line*, items split only on explicit
    delimiters (comma / semicolon / pipe, outside parentheses).

    A line only becomes a skill record when every item looks like a short
    skill name. A sentence, accomplishment, or project description that
    ended up under a skills heading is kept as an `other` record flagged
    for review -- never promoted to a skill.
    """
    facts: list[ExtractedFact] = []
    for line in lines:
        if not line.strip() or is_noise_line(line):
            continue
        content = strip_bullet(line)
        if not content:
            continue

        category = "Skills"
        rest = content
        if ":" in content:
            left, right = content.split(":", 1)
            left = left.strip()
            if 0 < len(left) <= _MAX_SKILL_CATEGORY_LEN and len(left.split()) <= 5 and right.strip():
                category = left
                rest = right.strip()

        items = split_skill_items(rest)
        if not items and rest and rest.lower() not in NOISE_KEYS:
            items = [rest]
        if not items:
            continue

        if all(item_looks_like_skill(item) for item in items):
            facts.append(
                ExtractedFact(
                    fact_type=FactType.SKILL,
                    fact_key=category,
                    fact_value={"items": items},
                    raw_text=line.strip(),
                )
            )
        else:
            facts.append(
                _skills_review_fact(
                    content,
                    line.strip(),
                    "This line is under a skills heading but reads like a sentence, not a skill list.",
                )
            )
    return facts


def _parse_achievement_section(lines: list[str]) -> list[ExtractedFact]:
    """One record per organization/activity, with its following description.

    A heading line plus the bullets (or one description paragraph)
    immediately under it become a single achievement. Isolated bullets
    stay their own record. Nothing is marked verified.
    """
    facts: list[ExtractedFact] = []
    current_heading: str | None = None
    current_bullets: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_bullets
        if current_heading is None and not current_bullets:
            return
        heading = current_heading or current_bullets[0]
        bullets = list(current_bullets)
        raw_parts = [current_heading] if current_heading else []
        raw_parts.extend(f"- {b}" for b in bullets)
        raw = "\n".join(raw_parts)
        reasons = [] if current_heading else ["No organization or activity name precedes this description."]
        facts.append(
            ExtractedFact(
                fact_type=FactType.ACHIEVEMENT,
                fact_key=heading[:150],
                fact_value={
                    "organization": current_heading,
                    "text": " ".join(bullets) if bullets else current_heading,
                    "bullets": bullets,
                    "raw_block": raw,
                    **review_fields(reasons, [] if current_heading else ["organization"]),
                },
                raw_text=raw,
            )
        )
        current_heading = None
        current_bullets = []

    for line in lines:
        if not line.strip() or is_noise_line(line):
            continue
        if is_bullet_line(line):
            content = strip_bullet(line)
            if content:
                current_bullets.append(content)
            continue
        if current_heading is not None and not current_bullets and looks_like_prose(line):
            current_bullets.append(line.strip())
            continue
        if current_heading is not None or current_bullets:
            flush()
        current_heading = line.strip()
    flush()
    return facts
