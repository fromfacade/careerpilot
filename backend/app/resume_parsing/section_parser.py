"""Deterministic, rule-based resume section parsing.

No AI, no network calls, no guessing of facts not present in the text.
Dates are kept as whatever substring was actually matched in the resume --
never parsed/rounded into a specific `date` value, since that would risk
asserting a precision the source text doesn't actually have.

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
from dataclasses import dataclass, field

from app.models.enums import FactType

_BULLET_CHARS = "-•*‣●▪◦‒–"

# Keyword phrases are matched against a normalized (lowercased, punctuation
# stripped) full line -- see _normalize_header_candidate. Order within a
# list doesn't matter; order of the dict does not affect matching, only
# iteration when building the combined lookup below.
_SECTION_HEADER_KEYWORDS: dict[FactType, tuple[str, ...]] = {
    FactType.EDUCATION: ("education", "academic background"),
    FactType.WORK_EXPERIENCE: (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "relevant experience",
    ),
    FactType.PROJECT: ("projects", "personal projects", "academic projects", "selected projects"),
    FactType.SKILL: (
        "skills",
        "technical skills",
        "skills and technologies",
        "technologies",
        "programming skills",
        "core competencies",
    ),
    FactType.ACHIEVEMENT: (
        "achievements",
        "awards",
        "honors",
        "honors and awards",
        "awards and honors",
        "certifications",
        "activities",
        "leadership",
        "activities and leadership",
    ),
}
_HEADER_LOOKUP: dict[str, FactType] = {
    keyword: fact_type for fact_type, keywords in _SECTION_HEADER_KEYWORDS.items() for keyword in keywords
}
_MAX_HEADER_LABEL_LEN = 35

_DATE_TOKEN = r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4})"
_DATE_RANGE_RE = re.compile(
    rf"{_DATE_TOKEN}\s*(?:-|–|—|to)\s*(?:{_DATE_TOKEN}|present|current)",
    re.IGNORECASE,
)


@dataclass
class ExtractedFact:
    fact_type: FactType
    fact_key: str
    fact_value: dict = field(default_factory=dict)
    raw_text: str = ""


def parse_resume_text(text: str) -> list[ExtractedFact]:
    """Segment raw resume text into `ExtractedFact` objects.

    Always returns at least one fact for any non-empty input: if section
    headers can't be found (or every detected section turns out empty),
    the fallback is a single `FactType.OTHER` fact holding the full text,
    never an empty list and never a fabricated structure.
    """
    text = text.strip()
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
            facts.extend(_parse_line_items_section(section_lines, FactType.ACHIEVEMENT))
        else:
            facts.extend(_parse_blocked_section(section_lines, fact_type))

    if not facts:
        # Headers existed but every section was empty -- still don't lose
        # the content silently; fall back to surfacing the raw text.
        return [_fallback_fact(text)]
    return facts


def _fallback_fact(text: str) -> ExtractedFact:
    return ExtractedFact(
        fact_type=FactType.OTHER,
        fact_key="Unstructured resume text",
        fact_value={"text": text},
        raw_text=text,
    )


def _normalize_header_candidate(line: str) -> str:
    normalized = line.strip().lower().replace("&", "and")
    normalized = re.sub(r"[^a-z ]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _find_headers(lines: list[str]) -> list[tuple[int, FactType, str | None]]:
    """Return `(line_index, fact_type, inline_remainder_after_colon)` for
    every line recognized as a section header, in document order."""
    found: list[tuple[int, FactType, str | None]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        inline_remainder: str | None = None
        header_candidate = stripped
        if ":" in stripped:
            left, right = stripped.split(":", 1)
            header_candidate = left
            inline_remainder = right.strip() or None

        if len(header_candidate) > _MAX_HEADER_LABEL_LEN:
            continue

        normalized = _normalize_header_candidate(header_candidate)
        fact_type = _HEADER_LOOKUP.get(normalized)
        if fact_type is not None:
            found.append((i, fact_type, inline_remainder))
    return found


def _is_bullet_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped[0] in _BULLET_CHARS


def _strip_bullet(line: str) -> str:
    stripped = line.strip()
    if stripped and stripped[0] in _BULLET_CHARS:
        stripped = stripped[1:].strip()
    return stripped


def _split_into_blocks(lines: list[str]) -> list[list[str]]:
    """Split a section's lines into per-entry blocks on blank lines, with
    a secondary heuristic (new entry starts right after a bullet line
    ends) when the author didn't use blank lines at all. If neither
    signal confidently finds more than one block, the whole section is
    returned as a single block -- a safe fallback that never invents
    structure that isn't actually there."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    if len(blocks) > 1:
        return blocks
    if len(blocks) == 1:
        secondary = _split_single_block_heuristically(blocks[0])
        if len(secondary) > 1:
            return secondary
    return blocks


def _split_single_block_heuristically(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    prev_was_bullet = False
    for line in lines:
        if line.strip() == "":
            continue
        starts_new_entry = prev_was_bullet and not _is_bullet_line(line)
        if starts_new_entry and current:
            blocks.append(current)
            current = []
        current.append(line)
        prev_was_bullet = _is_bullet_line(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_blocked_section(lines: list[str], fact_type: FactType) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for block in _split_into_blocks(lines):
        non_empty = [line for line in block if line.strip()]
        if not non_empty:
            continue

        block_text = "\n".join(non_empty)
        bullets = [_strip_bullet(line) for line in non_empty if _is_bullet_line(line)]
        date_match = _DATE_RANGE_RE.search(block_text)

        facts.append(
            ExtractedFact(
                fact_type=fact_type,
                fact_key=non_empty[0].strip()[:150],
                fact_value={
                    "raw_block": block_text,
                    "bullets": bullets,
                    "dates_text": date_match.group(0) if date_match else None,
                },
                raw_text=block_text,
            )
        )
    return facts


def _parse_skills_section(lines: list[str]) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for line in lines:
        if not line.strip():
            continue
        content = _strip_bullet(line)
        if not content:
            continue

        category = "Skills"
        rest = content
        if ":" in content:
            left, right = content.split(":", 1)
            if len(left.strip()) <= _MAX_HEADER_LABEL_LEN:
                category = left.strip()
                rest = right.strip()

        items = [item.strip() for item in re.split(r"[,;|•·]", rest) if item.strip()]
        if not items:
            continue

        facts.append(
            ExtractedFact(
                fact_type=FactType.SKILL,
                fact_key=category,
                fact_value={"items": items},
                raw_text=line.strip(),
            )
        )
    return facts


def _parse_line_items_section(lines: list[str], fact_type: FactType) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for line in lines:
        if not line.strip():
            continue
        content = _strip_bullet(line)
        if not content:
            continue
        facts.append(
            ExtractedFact(
                fact_type=fact_type,
                fact_key=content[:150],
                fact_value={"text": content},
                raw_text=line.strip(),
            )
        )
    return facts
