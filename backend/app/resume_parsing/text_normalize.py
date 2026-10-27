"""Repair unusual whitespace produced by PDF/DOCX text extraction, and host
the small text primitives (section headings, dates, bullets) shared by the
extractor and the section/entry parsers.

Google Docs / Word-exported PDFs often store each word as its own text
run. pypdf's default "plain" extractor then emits one token per line,
sometimes with a blank line between every word. The section parser used
to treat each of those lines as a separate candidate fact.

This module is deterministic and offline. It never invents words -- it
only joins tokens that were already adjacent in the extracted stream and
collapses redundant whitespace.
"""

from __future__ import annotations

import re

from app.models.enums import FactType

BULLET_CHARS = "-•*‣●▪◦‒–"
# Characters that are unambiguously list bullets when they appear *inside*
# a line that already starts with a bullet (layout mode sometimes glues two
# bullets onto one line). "-" / "*" / dashes are excluded: they appear in
# ordinary prose and ranges.
_INLINE_BULLET_CHARS = "•●▪◦‣"
_BULLET_CHARS = BULLET_CHARS  # backwards-compatible alias

_SECTION_HEADER_KEYWORDS: dict[FactType, tuple[str, ...]] = {
    FactType.EDUCATION: ("education", "academic background", "education and training"),
    FactType.WORK_EXPERIENCE: (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "relevant experience",
        "technical experience",
        "work history",
    ),
    FactType.PROJECT: (
        "projects",
        "personal projects",
        "academic projects",
        "selected projects",
        "technical projects",
        "relevant projects",
    ),
    FactType.SKILL: (
        "skills",
        "technical skills",
        "technical skill",
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
        "leadership and activities",
        "extracurricular activities",
        "extracurriculars",
        "leadership experience",
        "clubs and activities",
    ),
}
HEADER_LOOKUP: dict[str, FactType] = {
    keyword: fact_type for fact_type, keywords in _SECTION_HEADER_KEYWORDS.items() for keyword in keywords
}
_MAX_HEADER_LABEL_LEN = 35

# "Technologies: Python, FastAPI" under a project is a *field label*, not a
# new Skills section. Ambiguous labels only count as a section heading when
# they stand alone on their line in ALL CAPS ("TECHNOLOGIES").
_AMBIGUOUS_HEADER_LABELS = frozenset({"technologies"})

_FRAGMENTATION_THRESHOLD = 0.6
_MIN_LINES_TO_JUDGE_FRAGMENTATION = 8

# Real month names only (with the usual abbreviations). A loose `mar[a-z]*`
# would also match "Marketing" and `jun[a-z]*` would match "Junior".
MONTH = (
    r"(?<![A-Za-z])(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![A-Za-z])"
)
_SEASON = r"(?:spring|summer|fall|autumn|winter)"
DATE_TOKEN = rf"(?:{MONTH}\.?\s+\d{{4}}|{_SEASON}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_RANGE_SEP = r"(?:-|–|—|to)"
# `June – August 2024` (shared year) is also a common range shape.
DATE_RANGE_RE = re.compile(
    rf"(?:{DATE_TOKEN}\s*{_RANGE_SEP}\s*(?:{DATE_TOKEN}|present|current|now|ongoing)"
    rf"|{MONTH}\.?\s*{_RANGE_SEP}\s*{MONTH}\.?\s+\d{{4}})",
    re.IGNORECASE,
)
DATE_TOKEN_RE = re.compile(DATE_TOKEN, re.IGNORECASE)
_MONTH = MONTH
_DATE_TOKEN = DATE_TOKEN
_DATE_RANGE_RE = DATE_RANGE_RE

# `Santa Cruz, CA` or a bare work-mode word. Two-letter region codes only:
# `Acme, Inc` / `Foo, LLC` must not be mistaken for a location.
LOCATION_RE = re.compile(
    r"(?:[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*)*,\s*[A-Z]{2}(?:,\s*(?:USA|US))?"
    r"|Remote|Hybrid|On-?site)"
    r"(?:\s*\((?:Remote|Hybrid|On-?site)\))?",
)
_LOCATION_RE = re.compile(r",\s*[A-Z]{2}\b")

_DASH_SPLIT_RE = re.compile(r"\s+[—–-]\s+")


def fragmentation_score(text: str) -> float:
    """Share of nonempty lines that are a single token. 1.0 means every
    nonempty line is one word -- the Google-Docs-PDF failure mode."""
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if not nonempty:
        return 0.0
    single = sum(1 for line in nonempty if len(line.split()) == 1)
    return single / len(nonempty)


def _normalize_header_candidate(line: str) -> str:
    normalized = line.strip().lower().replace("&", "and")
    normalized = re.sub(r"[^a-z ]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def match_section_header(line: str) -> tuple[FactType, str | None] | None:
    """Return `(section_type, inline_remainder)` if `line` is a section
    heading, else None.

    A heading is the whole line (optionally followed by a colon, with the
    stray space PDFs insert: `EDUCATION :`). `Skills: Python, Go` is also
    accepted -- the text after the colon is returned as the remainder.
    Ambiguous labels such as `Technologies:` are field labels inside
    projects, never headings, unless written alone in ALL CAPS.
    """
    stripped = line.strip()
    if not stripped:
        return None
    label, _, remainder = stripped.partition(":")
    label = label.strip()
    remainder_text = remainder.strip() or None
    if not label or len(label) > _MAX_HEADER_LABEL_LEN:
        return None
    # A bullet line is content, never a heading.
    if label[0] in BULLET_CHARS:
        return None
    normalized = _normalize_header_candidate(label)
    section = HEADER_LOOKUP.get(normalized)
    if section is None:
        return None
    if normalized in _AMBIGUOUS_HEADER_LABELS and (remainder_text is not None or not label.isupper()):
        return None
    return section, remainder_text


def _is_section_header(line: str) -> bool:
    return match_section_header(line) is not None


def is_bullet_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped[0] in BULLET_CHARS


def strip_bullet(line: str) -> str:
    stripped = line.strip()
    if stripped and stripped[0] in BULLET_CHARS:
        stripped = stripped[1:].strip()
    return stripped


_is_bullet_line = is_bullet_line


def looks_like_sentence_fragment(line: str) -> bool:
    """Wrapped leftover of the previous bullet rather than a new heading:
    lowercase starts and one- or two-token tails ending in a period."""
    stripped = line.strip()
    if not stripped or is_bullet_line(stripped):
        return False
    if stripped[0].islower():
        return True
    return len(stripped.split()) <= 2 and stripped.endswith(".")


def looks_like_project_title(line: str) -> bool:
    """`TaskFlow - Backend Job Processing & Authentication Platform`."""
    stripped = line.strip()
    if not stripped or is_bullet_line(stripped) or _is_section_header(stripped):
        return False
    if DATE_RANGE_RE.fullmatch(stripped):
        return False
    if not _DASH_SPLIT_RE.search(stripped):
        return False
    left = _DASH_SPLIT_RE.split(stripped, maxsplit=1)[0].strip()
    if not left or left[0].islower():
        return False
    if re.match(MONTH, left, re.IGNORECASE) or re.fullmatch(r"\d{4}", left):
        return False
    return 1 <= len(left.split()) <= 8


def looks_like_job_header(line: str) -> bool:
    """`LSS Tutoring Services - Santa Cruz, CA September 2024 - Present`.

    A bare date range (`Jun 2024 - Aug 2024`) is not a new job.
    """
    stripped = line.strip()
    if not stripped or is_bullet_line(stripped) or _is_section_header(stripped):
        return False
    if stripped[0].islower():
        return False
    if DATE_RANGE_RE.fullmatch(stripped):
        return False
    has_location = bool(_LOCATION_RE.search(stripped))
    has_dates = bool(DATE_RANGE_RE.search(stripped))
    has_dash = bool(_DASH_SPLIT_RE.search(stripped))
    if has_location and (has_dash or has_dates):
        return True
    if has_dash and has_dates:
        left = _DASH_SPLIT_RE.split(stripped, maxsplit=1)[0].strip()
        if re.match(MONTH, left, re.IGNORECASE):
            return False
        return bool(left)
    return False


def _is_wrap_continuation(previous: str, current: str) -> bool:
    """True when `current` is the rest of `previous`, not a new record."""
    if not previous or not current:
        return False
    if _is_section_header(current) or is_bullet_line(current):
        return False
    if looks_like_project_title(current) or looks_like_job_header(current):
        return False

    # Date wrap: "... September 2024 - June" + "2025"
    if re.search(rf"{MONTH}\.?\s*$", previous, re.IGNORECASE) and re.fullmatch(r"\d{4}", current):
        return True
    if re.search(r"graduation\s*$", previous, re.IGNORECASE) and re.search(
        rf"^(?:{MONTH}\.?\s+\d{{4}}|\d{{4}})", current, re.IGNORECASE
    ):
        return True
    if current[0].islower():
        return True
    # Coursework / list wrap: previous line ended with a comma.
    if previous.rstrip().endswith(",") and not current[0].islower():
        return True
    # Short trailing fragment after a bullet ("patterns." / "coverage.")
    if is_bullet_line(previous) and current.endswith(".") and len(current.split()) <= 4:
        return True
    return False


def rejoin_wrapped_lines(text: str) -> str:
    """Attach PDF-wrapped tails to the line they belong to.

    Layout-mode extraction often breaks a bullet or date across two lines.
    We only join when the next line cannot be a new section/job/project.
    Words are never invented -- this only concatenates adjacent extracted
    lines with a single space.
    """
    out: list[str] = []
    for raw in text.splitlines():
        stripped = _collapse_horizontal_space(raw)
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and out[-1] and _is_wrap_continuation(out[-1], stripped):
            out[-1] = f"{out[-1]} {stripped}"
        else:
            out.append(stripped)
    return "\n".join(out)


def _collapse_horizontal_space(line: str) -> str:
    """Layout-mode extraction pads columns with runs of spaces. Collapse
    those to a single space so the parser sees real words, not gaps."""
    return re.sub(r"[ \t]{2,}", " ", line).strip()


def split_inline_bullets(text: str) -> str:
    """`• A. • B` on one line becomes two bullet lines.

    Only lines that *start* with a bullet are split, and only on real
    bullet glyphs surrounded by whitespace -- a skills row such as
    `Python • Go • Rust` (which does not start with a bullet) is left
    alone. No text is added or removed.
    """
    pattern = re.compile(rf"\s+(?=[{re.escape(_INLINE_BULLET_CHARS)}]\s)")
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped[0] in _INLINE_BULLET_CHARS and pattern.search(stripped):
            out.extend(part.strip() for part in pattern.split(stripped) if part.strip())
        else:
            out.append(line)
    return "\n".join(out)


def _rejoin_fragmented_tokens(text: str) -> str:
    """Join one-word-per-line streams back into readable lines.

    Blank lines are ignored while fragmented -- in the observed failure
    mode a blank sits between every word and is not a real paragraph
    break. Real structure is recovered from section headers and bullets.
    """
    out: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            out.append(" ".join(current))
            current.clear()

    for raw in text.splitlines():
        stripped = _collapse_horizontal_space(raw)
        if not stripped:
            continue
        if _is_section_header(stripped) or is_bullet_line(stripped):
            flush()
            out.append(stripped)
            continue
        if len(stripped.split()) >= 4:
            flush()
            out.append(stripped)
            continue
        current.append(stripped)
    flush()
    return "\n".join(out)


def normalize_extracted_text(text: str) -> str:
    """Collapse extraction artifacts without adding or dropping words.

    Always collapses horizontal space and 3+ consecutive newlines. If the
    text is still one-token-per-line, tokens on adjacent lines are joined
    with a single space. Section headers and bullet lines stay on their
    own line so the parser can still find structure. Lines that glued
    several bullets together are split back into one line per bullet.
    """
    if not text or not text.strip():
        return ""

    lines = [_collapse_horizontal_space(line) for line in text.replace("\r\n", "\n").splitlines()]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    nonempty = [line for line in collapsed.splitlines() if line.strip()]
    if (
        len(nonempty) >= _MIN_LINES_TO_JUDGE_FRAGMENTATION
        and fragmentation_score(collapsed) >= _FRAGMENTATION_THRESHOLD
    ):
        collapsed = _rejoin_fragmented_tokens(collapsed)
    collapsed = split_inline_bullets(collapsed)
    return rejoin_wrapped_lines(collapsed).strip()
