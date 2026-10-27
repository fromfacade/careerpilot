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


def flatten_tailored_lines(document: dict) -> list[str]:
    lines = [document.get("header", {}).get("full_name") or ""]
    for section in ("education", "work_experience", "projects", "skills", "achievements"):
        rows = document.get(section) or []
        if not rows:
            continue
        lines.append(section.replace("_", " ").title())
        for row in rows:
            lines.append(row.get("title") or "")
            detail = row.get("detail") or {}
            if isinstance(detail, dict):
                for value in detail.values():
                    if isinstance(value, list):
                        lines.extend(str(item) for item in value)
                    elif value:
                        lines.append(str(value))
            else:
                lines.append(str(detail))
    return [line for line in lines if line]
