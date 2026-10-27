"""Deterministic job-description analysis and qualification matching.

Requirements are marked `stated` when they come from an explicit section or
a clear keyword, otherwise `inferred`. A requirement is `satisfied` only
when a verified fact or an explicit profile field supports it.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import FactType, WorkAuthStatus
from app.models.job import Job

_TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")
_SECTION_RE = re.compile(
    r"(?im)^(requirements?|qualifications?|you['’]ll need|what you.?ll need|"
    r"preferred|nice to have|responsibilities|what you.?ll do|"
    r"education|experience|about the role)\s*:?\s*$"
)

_TECH = (
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c++",
    "c#",
    "sql",
    "fastapi",
    "django",
    "flask",
    "react",
    "vue",
    "angular",
    "node",
    "redis",
    "postgresql",
    "postgres",
    "mysql",
    "mongodb",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "linux",
    "git",
)

_AUTH_NEEDLES = ("authorized to work", "work authorization", "citizenship", "visa", "sponsorship")
_EDU_NEEDLES = ("bachelor", "master", "phd", "degree", "graduat")
_EXP_RE = re.compile(r"(\d+)\+?\s*(?:years?|yrs?)", re.I)
_STOP = frozenset({"and", "the", "with", "for", "you", "our", "this", "that", "from", "experience", "years"})


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall((text or "").casefold()) if tok not in _STOP}


def _lines(text: str) -> list[str]:
    return [re.sub(r"^[\-\*\u2022]\s*", "", line).strip() for line in (text or "").splitlines() if line.strip()]


def analyze_job_description(description: str, job: Job | None = None) -> dict:
    current = "other"
    buckets: dict[str, list[dict]] = {
        "required": [],
        "preferred": [],
        "responsibilities": [],
        "education": [],
        "experience": [],
        "technologies": [],
        "work_authorization": [],
        "location": [],
        "employment_type": [],
    }
    seen: set[str] = set()

    def add(kind: str, text: str, evidence: str) -> None:
        cleaned = " ".join(text.split())
        key = f"{kind}:{cleaned.casefold()}"
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        buckets[kind].append({"text": cleaned, "evidence": evidence})

    for line in _lines(description):
        heading = _SECTION_RE.match(line)
        if heading:
            label = heading.group(1).casefold()
            if "prefer" in label or "nice" in label:
                current = "preferred"
            elif "responsib" in label or "you’ll do" in label or "you'll do" in label:
                current = "responsibilities"
            elif "education" in label:
                current = "education"
            elif "experience" in label and "years" not in label:
                current = "experience"
            else:
                current = "required"
            continue
        if current in buckets:
            add(current, line, "stated")
        lowered = line.casefold()
        if any(needle in lowered for needle in _AUTH_NEEDLES):
            add("work_authorization", line, "stated")
        if any(needle in lowered for needle in _EDU_NEEDLES):
            add("education", line, "stated")
        years = _EXP_RE.search(line)
        if years:
            add("experience", line, "stated")
        for tech in _TECH:
            if re.search(rf"\b{re.escape(tech)}\b", lowered):
                add("technologies", tech, "stated")

    if job is not None:
        if job.employment_type and job.employment_type.value != "unknown":
            add("employment_type", job.employment_type.value.replace("_", " "), "stated")
        if job.remote_type and job.remote_type.value != "unknown":
            add("location", job.remote_type.value, "stated")
        for loc in getattr(job, "locations", []) or []:
            add("location", loc.raw_text, "stated")
        if job.role_category and job.role_category.value != "unknown":
            add("responsibilities", f"Role category: {job.role_category.value.replace('_', ' ')}", "inferred")

    return {
        "required": buckets["required"],
        "preferred": buckets["preferred"],
        "responsibilities": buckets["responsibilities"],
        "education": buckets["education"],
        "experience": buckets["experience"],
        "technologies": buckets["technologies"],
        "work_authorization": buckets["work_authorization"],
        "location": buckets["location"],
        "employment_type": buckets["employment_type"],
        "summary": (description or "").strip()[:600],
    }


def _fact_blob(facts: Iterable[CanonicalFact]) -> str:
    parts = []
    for fact in facts:
        parts.append(f"{fact.fact_key} {fact.fact_value}")
    return " ".join(parts)


def _profile_blob(candidate: Candidate) -> str:
    return " ".join(
        str(value)
        for value in (
            candidate.school,
            candidate.degree_level.value if candidate.degree_level else "",
            candidate.major,
            candidate.work_authorization_status.value if candidate.work_authorization_status else "",
            candidate.requires_sponsorship.value if candidate.requires_sponsorship else "",
            candidate.current_location,
        )
        if value
    )


def match_qualifications(analysis: dict, facts: list[CanonicalFact], candidate: Candidate) -> dict:
    allowed = f"{_fact_blob(facts)} {_profile_blob(candidate)}"
    allowed_tokens = _tokens(allowed)
    matches: list[dict] = []
    missing: list[dict] = []
    uncertain: list[dict] = []

    items: list[tuple[str, dict]] = []
    for group in ("required", "preferred", "technologies", "education", "experience", "work_authorization"):
        for item in analysis.get(group) or []:
            items.append((group, item))

    for group, item in items:
        text = item["text"]
        evidence = item.get("evidence", "inferred")
        tokens = _tokens(text) - {"or", "of", "in", "to"}
        overlap = tokens & allowed_tokens
        record = {
            "group": group,
            "text": text,
            "evidence": evidence,
            "supporting_tokens": sorted(overlap),
        }
        if group == "work_authorization":
            explicit = candidate.work_authorization_status not in {
                WorkAuthStatus.UNKNOWN,
                None,
            }
            if explicit and candidate.work_authorization_status in {
                WorkAuthStatus.US_CITIZEN,
                WorkAuthStatus.PERMANENT_RESIDENT,
            }:
                record["supporting_tokens"] = [candidate.work_authorization_status.value]
                matches.append(record)
            elif explicit:
                uncertain.append(record)
            else:
                missing.append({**record, "reason": "Work authorization is not stated on the candidate profile."})
            continue
        if overlap:
            matches.append(record)
        elif evidence == "inferred":
            uncertain.append({**record, "reason": "Inferred from the posting; no verified fact supports it."})
        else:
            missing.append({**record, "reason": "No verified fact or profile field supports this requirement."})

    return {
        "matched": matches,
        "missing": missing,
        "uncertain": uncertain,
        "verified_fact_count": len(facts),
    }
