"""Deterministic job-description analysis and qualification matching.

Requirements are marked `stated` when they come from an explicit section or
a clear keyword, otherwise `inferred`. A requirement is `satisfied` only
when a verified fact or an explicit profile field supports it. Absence of
evidence is unknown, not a confirmed gap.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import DegreeLevel, TriState, WorkAuthStatus
from app.models.job import Job

_TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")
_STOP = frozenset({"and", "the", "with", "for", "you", "our", "this", "that", "from", "experience", "years"})
_AUTH_NEEDLES = ("authorized to work", "work authorization", "citizenship", "visa", "sponsorship")
_EDU_NEEDLES = ("bachelor", "master", "phd", "degree", "graduat", "pursuing a ba", "pursuing a bs")
_EXP_RE = re.compile(r"(\d+)\+?\s*(?:years?|yrs?)", re.I)
_QUAL_CUES = (
    "experience with",
    "experience in",
    "proficien",
    "familiar",
    "coursework",
    "pursuing",
    "degree",
    "authorized",
    "available for",
    "knowledge of",
    "must have",
    "required",
    "internship",
)
_TECH = (
    "python",
    "java",
    "javascript",
    "typescript",
    "ruby",
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
_DEGREE_RANK = {
    DegreeLevel.ASSOCIATE: 1,
    DegreeLevel.BACHELORS: 2,
    DegreeLevel.MASTERS: 3,
    DegreeLevel.PHD: 4,
}
_DEGREE_NEEDLES = (
    (DegreeLevel.PHD, ("phd", "doctorate")),
    (DegreeLevel.MASTERS, ("master", "ms ", "m.s")),
    (DegreeLevel.BACHELORS, ("bachelor", "ba/bs", "b.s", "b.a", "undergraduate")),
)

# Longer, more specific headings first so "minimum requirements" wins over "requirements".
_HEADINGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\babout [A-Z][A-Za-z0-9&'.-]{1,40}\b"), "company"),
    (re.compile(r"(?i)\babout (?:the )?(?:company|role|team|position|us)\b"), "company"),
    (re.compile(r"(?i)\bwho we are\b|\bour mission\b|\bwhat we (?:do|offer)\b"), "company"),
    (re.compile(r"(?i)\bwhat you(?:'|’)?ll do\b|\bwhat you will do\b|\bresponsibilities\b|\bin this role\b"), "responsibilities"),
    (re.compile(r"(?i)\bpreferred(?: qualifications)?\b|\bnice to have\b|\bbonus points\b"), "preferred"),
    (
        re.compile(
            r"(?i)\bminimum (?:qualifications|requirements)\b|\bwho you are\b|"
            r"\bwhat (?:we(?:'|’)re|you(?:'|’)ll) looking for\b|"
            r"\bwhat you(?:'|’)?ll need\b|\brequirements?\b|\bqualifications?\b"
        ),
        "required",
    ),
    (re.compile(r"(?im)^education\s*:?\s*$"), "education"),
    (re.compile(r"(?im)^experience\s*:?\s*$"), "experience"),
    (re.compile(r"(?i)\bbenefits\b|\bperks\b|\bcompensation\b"), "benefits"),
]


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall((text or "").casefold()) if tok not in _STOP}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _lines(text: str) -> list[str]:
    return [re.sub(r"^[\-\*\u2022]\s*", "", line).strip() for line in (text or "").splitlines() if line.strip()]


def _split_items(body: str) -> list[str]:
    lines = _lines(body)
    if not lines:
        return []
    if len(lines) == 1 and re.search(r"[.;]\s+", lines[0]):
        return [part.strip(" .;") for part in re.split(r"(?<=[.;])\s+", lines[0]) if part.strip(" .;")]
    return lines


def _heading_spans(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for pattern, kind in _HEADINGS:
        for match in pattern.finditer(text):
            found.append((match.start(), match.end(), kind))
    found.sort()
    spans: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, kind in found:
        if start < last_end:
            continue
        spans.append((start, end, kind))
        last_end = end
    return spans


def _section_chunks(description: str) -> list[tuple[str, str]]:
    text = (description or "").strip()
    if not text:
        return []
    spans = _heading_spans(text)
    if not spans:
        return [("other", text)]
    chunks: list[tuple[str, str]] = []
    if spans[0][0] > 0:
        preface = text[: spans[0][0]].strip()
        if preface:
            chunks.append(("company" if len(preface) > 160 else "other", preface))
    for index, (start, end, kind) in enumerate(spans):
        stop = spans[index + 1][0] if index + 1 < len(spans) else len(text)
        body = text[end:stop].strip(" \t:-")
        if body:
            chunks.append((kind, body))
    return chunks


def _is_qualification_line(text: str) -> bool:
    if len(text) < 3:
        return False
    lowered = text.casefold()
    if any(cue in lowered for cue in _QUAL_CUES) or _EXP_RE.search(text):
        return True
    return len(text) <= 220


def _is_marketing(text: str) -> bool:
    return len(text) > 240 and not any(cue in text.casefold() for cue in _QUAL_CUES)


def analyze_job_description(description: str, job: Job | None = None) -> dict:
    buckets: dict[str, list[dict]] = {
        "company": [],
        "required": [],
        "preferred": [],
        "responsibilities": [],
        "education": [],
        "experience": [],
        "technologies": [],
        "work_authorization": [],
        "location": [],
        "employment_type": [],
        "benefits": [],
    }
    seen: set[str] = set()

    def add(kind: str, text: str, evidence: str) -> None:
        cleaned = _clean(text)
        key = f"{kind}:{cleaned.casefold()}"
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        buckets[kind].append({"text": cleaned, "evidence": evidence})

    qualification_kinds = {"required", "preferred", "education", "experience"}
    tech_kinds = {"required", "preferred", "responsibilities", "education", "experience"}

    for kind, body in _section_chunks(description):
        for line in _split_items(body) or [_clean(body)]:
            if kind in {"company", "benefits"} or (kind == "other" and _is_marketing(line)):
                add("company" if kind != "benefits" else "benefits", line, "stated")
                continue
            if kind == "responsibilities":
                add("responsibilities", line, "stated")
            elif kind in qualification_kinds:
                if _is_marketing(line):
                    add("company", line, "inferred")
                    continue
                if _is_qualification_line(line):
                    add(kind, line, "stated")
                else:
                    add("company", line, "inferred")
            elif any(cue in line.casefold() for cue in _QUAL_CUES) or _EXP_RE.search(line):
                add("required", line, "inferred")
            else:
                add("company", line, "inferred")

            if kind not in tech_kinds and kind not in qualification_kinds:
                continue
            lowered = line.casefold()
            if kind in qualification_kinds:
                if any(needle in lowered for needle in _AUTH_NEEDLES):
                    add("work_authorization", line, "stated")
                if any(needle in lowered for needle in _EDU_NEEDLES):
                    add("education", line, "stated")
                if _EXP_RE.search(line):
                    add("experience", line, "stated")
            if kind in tech_kinds:
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

    company_summary = " ".join(item["text"] for item in buckets["company"][:2]).strip()
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
        "company": buckets["company"],
        "benefits": buckets["benefits"],
        "summary": company_summary[:600] or _clean(description)[:400],
    }


def employer_context(analysis: dict, employer: str, title: str) -> str:
    parts = [f"Employer: {employer}", f"Role: {title}"]
    for group in ("company", "responsibilities"):
        for item in analysis.get(group) or []:
            if item.get("text"):
                parts.append(str(item["text"]))
    return "\n".join(parts)[:1500]


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


def _required_degree(text: str) -> DegreeLevel | None:
    lowered = text.casefold()
    for level, needles in _DEGREE_NEEDLES:
        if any(needle in lowered for needle in needles):
            return level
    return None


def _contradicts(group: str, text: str, candidate: Candidate) -> str | None:
    lowered = text.casefold()
    if group == "work_authorization":
        no_sponsor = any(phrase in lowered for phrase in ("not sponsor", "unable to sponsor", "no visa", "cannot sponsor"))
        if no_sponsor and candidate.requires_sponsorship is TriState.YES:
            return "The posting does not offer sponsorship, and the profile states sponsorship is required."
        if "citizen" in lowered and candidate.work_authorization_status in {
            WorkAuthStatus.VISA_HOLDER,
            WorkAuthStatus.REQUIRES_SPONSORSHIP,
        }:
            return "The posting asks for citizenship, which the verified profile does not state."
    if group == "education":
        needed = _required_degree(text)
        have = candidate.degree_level
        if needed and have in _DEGREE_RANK and _DEGREE_RANK[have] < _DEGREE_RANK[needed]:
            return f"The posting asks for a {needed.value} and the verified profile lists {have.value}."
    return None


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
        contradiction = _contradicts(group, text, candidate)
        if contradiction:
            missing.append({**record, "reason": contradiction})
            continue
        if group == "work_authorization":
            explicit = candidate.work_authorization_status not in {WorkAuthStatus.UNKNOWN, None}
            if explicit and candidate.work_authorization_status in {
                WorkAuthStatus.US_CITIZEN,
                WorkAuthStatus.PERMANENT_RESIDENT,
            }:
                record["supporting_tokens"] = [candidate.work_authorization_status.value]
                matches.append(record)
            else:
                uncertain.append({**record, "reason": "Work authorization is unknown until the candidate confirms it."})
            continue
        if overlap:
            matches.append(record)
        else:
            uncertain.append(
                {
                    **record,
                    "reason": "Unknown: no verified fact addresses this requirement, so it is not treated as missing.",
                }
            )

    return {
        "matched": matches,
        "missing": missing,
        "uncertain": uncertain,
        "verified_fact_count": len(facts),
    }
