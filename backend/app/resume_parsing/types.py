"""Plain data types shared by the resume parsing modules (kept separate so
`section_parser` and `entry_parser` can both use them without importing
each other)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import FactType


@dataclass
class ExtractedFact:
    fact_type: FactType
    fact_key: str
    fact_value: dict = field(default_factory=dict)
    raw_text: str = ""


def review_fields(reasons: list[str], ambiguous_fields: list[str]) -> dict:
    """Uniform review-flag payload merged into `fact_value`.

    `needs_review` is true whenever the parser could not confidently
    assign a required field. The reasons / field names are shown to the
    human reviewer; nothing here ever marks a fact verified.
    """
    return {
        "needs_review": bool(reasons or ambiguous_fields),
        "review_reasons": list(reasons),
        "ambiguous_fields": list(dict.fromkeys(ambiguous_fields)),
    }
