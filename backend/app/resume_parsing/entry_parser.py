"""Work-experience and project parsing.

Both sections are a sequence of *entries*: a few header lines (who/what,
where, when, tech stack) followed by bullets. Segmentation never relies on
a single formatting convention:

* Once an entry has bullets, the next non-bullet line is a new entry.
* Before bullets, a line starts a new entry only when the current entry's
  header is already complete (it has dates and a role/name) or a blank
  line separates them.
* Location- and date-only lines (`Santa Cruz, CA | September 2024 -
  Present`) always belong to the entry they follow -- they are metadata,
  never an employer.

Field assignment is conservative. If employer vs. position (or a project
name) cannot be told apart from the text, the field is left empty, the
verbatim header lines are kept, and the record is flagged `needs_review`
with the reason. Nothing is guessed and nothing is marked verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import FactType
from app.resume_parsing.skill_items import is_noise_line, looks_like_tech_list, split_skill_items
from app.resume_parsing.text_normalize import (
    DATE_RANGE_RE,
    DATE_TOKEN_RE,
    LOCATION_RE,
    is_bullet_line,
    looks_like_project_title,
    looks_like_sentence_fragment,
    match_section_header,
    strip_bullet,
)
from app.resume_parsing.types import ExtractedFact, review_fields

_TITLE_HINT_RE = re.compile(
    r"\b(intern|engineer|developer|analyst|assistant|associate|manager|researcher|tutor|fellow|"
    r"technician|specialist|consultant|lead|member|crew|director|coordinator|representative|"
    r"officer|president|chair|founder|co-founder|architect|scientist|instructor|mentor|counselor|"
    r"apprentice|programmer|designer|administrator|volunteer|ambassador|captain|trainee|co-op|"
    r"clerk|cashier|barista|bartender|supervisor|teacher|aide|advisor|adviser|operator|secretary|"
    r"treasurer|editor|writer|accountant|recruiter|receptionist|lifeguard)\b",
    re.IGNORECASE,
)
_TECH_LABEL_RE = re.compile(
    r"^(?:tech(?:nolog(?:y|ies))?(?:\s+(?:used|stack))?|stack|tools?(?:\s+used)?|built\s+with|"
    r"languages?\s*(?:and|&|/)\s*frameworks?)\s*[:\-—–]\s*(.+)$",
    re.IGNORECASE,
)
_SEGMENT_SPLIT_RE = re.compile(r"\s*\|\s*|\s+[—–-]\s+|\s+[•·]\s+")
_SPACED_DASH_RE = re.compile(r"\s+[—–-]\s+")
_EDGE_PUNCT = " ,;:|•·–—-"


@dataclass
class _Entry:
    header: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)


@dataclass
class _Parts:
    text: list[str]
    location: str | None
    dates: str | None


def _strip_dates(line: str) -> tuple[str, str | None]:
    match = DATE_RANGE_RE.search(line)
    if not match:
        return line, None
    return f"{line[: match.start()]} | {line[match.end():]}", match.group(0)


def _classify_line(line: str) -> _Parts:
    """Split one header line into text segments, a location, and dates."""
    work, dates = _strip_dates(line.strip())
    text: list[str] = []
    location: str | None = None
    for segment in _SEGMENT_SPLIT_RE.split(work):
        segment = segment.strip(_EDGE_PUNCT)
        if not segment:
            continue
        if dates is None and DATE_TOKEN_RE.fullmatch(segment):
            dates = segment
            continue
        if LOCATION_RE.fullmatch(segment):
            location = location or segment
            continue
        text.append(segment)
    return _Parts(text=text, location=location, dates=dates)


def looks_like_prose(line: str) -> bool:
    words = len(line.split())
    if line.endswith(".") and words >= 4:
        return True
    return words >= 12 and "|" not in line and not _SPACED_DASH_RE.search(line)


def _has_title_hint(text: str) -> bool:
    return bool(_TITLE_HINT_RE.search(text))


def _is_title_line(line: str) -> bool:
    return (
        looks_like_project_title(line)
        and not line.rstrip().endswith(".")
        and not _TECH_LABEL_RE.match(line)
        and match_section_header(line) is None
    )


def _work_starts_new_entry(entry: _Entry, line: str, saw_blank: bool) -> bool:
    if entry.bullets:
        return True
    parts = _classify_line(line)
    if not parts.text:
        return False  # location/date-only line: metadata of the current entry
    current = [_classify_line(h) for h in entry.header]
    current_text = [t for p in current for t in p.text]
    if not current_text:
        return False
    if any(p.dates for p in current):
        has_position = any(_has_title_hint(t) for t in current_text)
        if not has_position and parts.dates is None and _has_title_hint(" ".join(parts.text)):
            return False  # `Org - City, ST dates` followed by its position line
        return True
    return saw_blank


def _project_starts_new_entry(entry: _Entry, line: str, saw_blank: bool) -> bool:
    if entry.bullets:
        return True
    if not entry.header:
        return False
    first_is_title = _is_title_line(entry.header[0])
    if _is_title_line(line) and (first_is_title or len(entry.header) >= 2):
        return True
    if saw_blank and not looks_like_prose(line):
        parts = _classify_line(line)
        is_meta = not parts.text
        is_tech = bool(_TECH_LABEL_RE.match(line)) or looks_like_tech_list(line, max_words=3)
        return not (is_meta or is_tech)
    return False


def _segment(lines: list[str], kind: FactType) -> list[_Entry]:
    starts_new = _work_starts_new_entry if kind is FactType.WORK_EXPERIENCE else _project_starts_new_entry
    entries: list[_Entry] = []
    current: _Entry | None = None
    saw_blank = False

    for raw in lines:
        line = raw.strip()
        if not line:
            saw_blank = True
            continue
        if is_noise_line(line):
            continue
        if is_bullet_line(line):
            current = current or _Entry()
            current.bullets.append(strip_bullet(line))
            current.raw.append(line)
            saw_blank = False
            continue
        if current is not None and current.bullets and looks_like_sentence_fragment(line):
            # A wrapped tail that normalization could not attach: keep it
            # with the bullet it continues rather than starting a record.
            current.bullets[-1] = f"{current.bullets[-1]} {line}"
            current.raw[-1] = f"{current.raw[-1]} {line}"
            saw_blank = False
            continue
        if current is not None and current.header and not current.bullets and looks_like_prose(line):
            # An unbulleted description line under the header.
            current.bullets.append(line)
            current.raw.append(line)
            saw_blank = False
            continue
        if current is not None and starts_new(current, line, saw_blank):
            entries.append(current)
            current = None
        current = current or _Entry()
        current.header.append(line)
        current.raw.append(line)
        saw_blank = False

    if current is not None and (current.header or current.bullets):
        entries.append(current)
    return entries


def _split_single_role(text: str) -> tuple[str | None, str | None]:
    """`Intern, Acme Corp` / `Intern at Acme Corp` -> (employer, position)."""
    for pattern in (r"\s+at\s+", r",\s+"):
        split = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE)
        if len(split) != 2:
            continue
        left, right = split[0].strip(), split[1].strip()
        if _has_title_hint(left) and not _has_title_hint(right):
            return right, left
        if _has_title_hint(right) and not _has_title_hint(left):
            return left, right
    return None, None


def _assign_roles(text: list[str]) -> tuple[str | None, str | None, list[str]]:
    """Return `(employer, position, unclassified_text)` for header text parts."""
    if not text:
        return None, None, []
    if len(text) == 1:
        only = text[0]
        employer, position = _split_single_role(only)
        if employer or position:
            return employer, position, []
        return (None, only, []) if _has_title_hint(only) else (only, None, [])
    if len(text) == 2:
        first_hint, second_hint = _has_title_hint(text[0]), _has_title_hint(text[1])
        if second_hint and not first_hint:
            return text[0], text[1], []
        if first_hint and not second_hint:
            return text[1], text[0], []
    return None, None, list(text)


def _bullets_and_raw(entry: _Entry) -> tuple[list[str], str]:
    return list(entry.bullets), "\n".join(entry.raw)


def _structure_work(entry: _Entry) -> ExtractedFact | None:
    if not entry.header and not entry.bullets:
        return None
    parts = [_classify_line(line) for line in entry.header]
    dates = next((p.dates for p in parts if p.dates), None)
    location = next((p.location for p in parts if p.location), None)
    text = [t for p in parts for t in p.text]
    employer, position, unclassified = _assign_roles(text)

    reasons: list[str] = []
    ambiguous: list[str] = []
    if unclassified:
        reasons.append(
            "Could not tell the employer from the position in: " + " / ".join(unclassified)
            if len(unclassified) > 1
            else "Could not classify this header line as employer or position."
        )
        ambiguous.extend(["employer", "position"])
    else:
        if employer is None:
            reasons.append("No employer found in this entry.")
            ambiguous.append("employer")
        if position is None:
            reasons.append("No position title found in this entry.")
            ambiguous.append("position")

    bullets, raw = _bullets_and_raw(entry)
    key = employer or position or (entry.header[0] if entry.header else "Work experience")
    value = {
        "employer": employer,
        "position": position,
        "location": location,
        "dates_text": dates,
        "bullets": bullets,
        "raw_block": raw,
        **review_fields(reasons, ambiguous),
    }
    if unclassified:
        value["unclassified_text"] = unclassified
    return ExtractedFact(fact_type=FactType.WORK_EXPERIENCE, fact_key=key[:150], fact_value=value, raw_text=raw)


def _carry_employer_forward(facts: list[ExtractedFact]) -> None:
    """A second position under one employer repeats no employer line.

    The employer is taken from the preceding record, but because the text
    for *this* record does not state it, the record is flagged for review.
    """
    for previous, current in zip(facts, facts[1:]):
        value = current.fact_value
        if value["employer"] is not None or value["position"] is None:
            continue
        if previous.fact_value["employer"] is None or value["dates_text"] is None:
            continue
        value["employer"] = previous.fact_value["employer"]
        value["location"] = value["location"] or previous.fact_value["location"]
        reasons = [r for r in value["review_reasons"] if r != "No employer found in this entry."]
        reasons.append("Employer carried over from the preceding position at the same employer; confirm it applies.")
        value.update(review_fields(reasons, [*value["ambiguous_fields"], "employer"]))
        current.fact_key = value["employer"][:150]


def parse_work_section(lines: list[str]) -> list[ExtractedFact]:
    facts = [fact for entry in _segment(lines, FactType.WORK_EXPERIENCE) if (fact := _structure_work(entry))]
    _carry_employer_forward(facts)
    return facts


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _structure_project(entry: _Entry) -> ExtractedFact | None:
    if not entry.header and not entry.bullets:
        return None

    name: str | None = None
    tagline: str | None = None
    technologies: list[str] = []
    dates: str | None = None
    summary: list[str] = []

    header = list(entry.header)
    if header and not _TECH_LABEL_RE.match(header[0]):
        first, first_dates = _strip_dates(header[0])
        first = first.strip(_EDGE_PUNCT)
        dates = first_dates
        paren = re.search(r"\(([^)]+)\)\s*$", first)
        if paren and "," in paren.group(1):
            technologies.extend(split_skill_items(paren.group(1)))
            first = first[: paren.start()]
        segments = [s.strip(_EDGE_PUNCT) for s in _SEGMENT_SPLIT_RE.split(first)]
        segments = [s for s in segments if s]
        if segments:
            name = segments[0]
            taglines: list[str] = []
            for segment in segments[1:]:
                if looks_like_tech_list(segment):
                    technologies.extend(split_skill_items(segment))
                else:
                    taglines.append(segment)
            tagline = " — ".join(taglines) or None
        header = header[1:]

    for line in header:
        labeled = _TECH_LABEL_RE.match(line)
        if labeled:
            technologies.extend(split_skill_items(labeled.group(1)))
            continue
        remainder, line_dates = _strip_dates(line)
        if line_dates and not remainder.strip(_EDGE_PUNCT):
            dates = dates or line_dates
            continue
        if not technologies and looks_like_tech_list(line, max_words=3):
            technologies.extend(split_skill_items(line))
            continue
        summary.append(line)

    reasons: list[str] = []
    ambiguous: list[str] = []
    if name is None:
        reasons.append("No project name found; the entry starts with its description or bullets.")
        ambiguous.append("name")

    bullets, raw = _bullets_and_raw(entry)
    key = name or (entry.header[0] if entry.header else bullets[0][:80])
    value = {
        "name": name,
        "tagline": tagline,
        "technologies": _dedupe(technologies),
        "dates_text": dates,
        "bullets": bullets,
        "raw_block": raw,
        **review_fields(reasons, ambiguous),
    }
    if summary:
        value["summary"] = summary
    return ExtractedFact(fact_type=FactType.PROJECT, fact_key=key[:150], fact_value=value, raw_text=raw)


def parse_project_section(lines: list[str]) -> list[ExtractedFact]:
    return [fact for entry in _segment(lines, FactType.PROJECT) if (fact := _structure_project(entry))]
