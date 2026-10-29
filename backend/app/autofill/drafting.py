"""Decide which Greenhouse questions may be drafted. No model calls."""

from __future__ import annotations

import re

from app.autofill.greenhouse import question_kind_for
from app.models.enums import AnswerCategory

_FACTUAL = frozenset({"gpa", "graduation_date", "start_date"})
_NARRATIVE = ("describe ", "tell us ", "tell me ", "explain ", "why ", "how ")
_WORD_LIMIT = re.compile(r"\b(\d{1,4})\s+words?\b", re.I)
_CHAR_LIMIT = re.compile(r"\b(\d{1,4})\s+characters?\b", re.I)

FACT_GAP = "Enter it yourself. CareerPilot will not guess."
MISSING_FACTS = (
    "No verified facts are available for this question. Add the missing information "
    "before a draft is written. CareerPilot will not guess."
)
GENERATION_FAILED = "The draft could not be generated. You can try again. Nothing was invented."


def draft_action(question_kind: str, label: str) -> str:
    """Return generate, fact, manual, or skip.

    Open-ended written questions can be drafted. GPA, graduation, and start
    dates stay factual. Sensitive and consent questions stay manual.
    """
    kind = question_kind or question_kind_for(label)
    if kind == "sensitive":
        return "manual"
    if kind in _FACTUAL:
        return "fact"
    if kind == "written_question":
        return "generate"
    normalized = " ".join(label.casefold().split())
    if kind == "experience" and normalized.startswith(_NARRATIVE) and "years" not in normalized:
        return "generate"
    return "skip"


def category_for(label: str) -> AnswerCategory:
    text = " ".join(label.casefold().split())
    if text.startswith("why ") or "interested" in text or "interest in" in text:
        return AnswerCategory.INTEREST
    if "experience with" in text or "technology" in text:
        return AnswerCategory.SKILLS
    return AnswerCategory.EXPERIENCE


def fact_gap_message(question_kind: str) -> str:
    subject = {
        "gpa": "GPA",
        "graduation_date": "graduation date",
        "start_date": "start date or availability",
    }.get(question_kind, "factual value")
    return f"This asks for a {subject}. No verified value is on file. {FACT_GAP}"


def limit_text(text: str, label: str) -> tuple[str, bool]:
    """Shorten a draft to a word or character limit written in the question."""
    limited = text.strip()
    word_limit = _WORD_LIMIT.search(label)
    if word_limit:
        count = int(word_limit.group(1))
        words = limited.split()
        if count > 0 and len(words) > count:
            limited = " ".join(words[:count])
    char_limit = _CHAR_LIMIT.search(label)
    if char_limit:
        count = int(char_limit.group(1))
        if count > 0 and len(limited) > count:
            clipped = limited[:count].rstrip()
            if " " in clipped:
                clipped = clipped.rsplit(" ", 1)[0]
            limited = clipped
    return limited, limited != text.strip()


def limit_note(label: str) -> str:
    parts: list[str] = []
    word_limit = _WORD_LIMIT.search(label)
    char_limit = _CHAR_LIMIT.search(label)
    if word_limit:
        parts.append(f"at most {int(word_limit.group(1))} words")
    if char_limit:
        parts.append(f"at most {int(char_limit.group(1))} characters")
    if not parts:
        return "Answer in one concise paragraph unless the question asks for detail."
    return "The answer must be " + " and ".join(parts) + "."
