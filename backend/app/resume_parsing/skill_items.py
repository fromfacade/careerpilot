"""Splitting of comma/pipe separated skill and technology lists.

Items are kept exactly as written: `Linux/Unix` and `Git/GitHub` stay one
item, commas inside parentheses do not split (`Cloud (AWS, GCP)`), and a
glued run like `PythonJavaScriptTypeScriptSQLC++` is split only by
consuming known skill names (never CamelCase, so `FastAPI` stays whole).
"""

from __future__ import annotations

KNOWN_SKILL_TOKENS = (
    "TypeScript",
    "JavaScript",
    "PostgreSQL",
    "SQLAlchemy",
    "Node.js",
    "Next.js",
    "Python",
    "SQL",
    "C++",
    "C#",
    "Go",
    "Rust",
    "Java",
    "HTML",
    "CSS",
    "AWS",
    "GCP",
)

# Single-token leftovers that must never become their own fact.
NOISE_KEYS = frozenset(
    {"-", "—", "–", "|", ",", ";", "&", "and", "or", "of", "the", "a", "an", "in", "to", "for", "with", "on", "at"}
)

_MAX_ITEM_WORDS = 5
_MAX_ITEM_CHARS = 45


def is_noise_line(line: str) -> bool:
    stripped = line.strip().strip(".,;:")
    return not stripped or stripped.lower() in NOISE_KEYS


def _split_top_level(text: str, separators: str = ",;|") -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char in separators and depth == 0:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer))
    return parts


def _split_glued_skill_token(token: str) -> list[str]:
    if " " in token or len(token) < 6:
        return [token]
    remaining = token
    parts: list[str] = []
    known = tuple(sorted(KNOWN_SKILL_TOKENS, key=len, reverse=True))
    while remaining:
        matched = next((name for name in known if remaining.startswith(name)), None)
        if matched is None:
            return [token]
        parts.append(matched)
        remaining = remaining[len(matched) :]
    return parts if len(parts) >= 2 else [token]


def split_skill_items(text: str) -> list[str]:
    items: list[str] = []
    for raw in _split_top_level(text):
        item = raw.strip(" \t•·")
        if not item or item.lower() in NOISE_KEYS:
            continue
        items.extend(_split_glued_skill_token(item))
    return items


def item_looks_like_skill(item: str) -> bool:
    """A skill/technology is a short noun phrase, not a sentence."""
    stripped = item.strip()
    if not stripped or len(stripped) > _MAX_ITEM_CHARS or len(stripped.split()) > _MAX_ITEM_WORDS:
        return False
    if stripped.endswith(".") and not stripped.lower().endswith(("etc.", "vs.")):
        # "Node.js" does not end with a period; "Built an API." does.
        return False
    return ": " not in stripped


def looks_like_tech_list(text: str, *, max_words: int = 4) -> bool:
    """A comma/pipe separated run of short items (`React, Next.js, Docker`)."""
    items = split_skill_items(text)
    if len(items) < 2:
        return False
    return all(1 <= len(item.split()) <= max_words and not item.endswith(".") for item in items)
