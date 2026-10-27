"""Deterministic resume-profile ranking. No model calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.enums import ResumeCategory, ResumeSelectionSource
from app.models.resume import CandidateFact, Resume

_TOKEN_RE = re.compile(r"[a-z0-9+#.]{2,}")
_STOP = frozenset({"and", "the", "with", "for", "you", "our", "this", "that", "from", "resume", "intern", "internship"})
_BACKEND = frozenset({"backend", "fastapi", "django", "flask", "postgres", "postgresql", "sql", "api", "redis", "taskflow"})
_FULLSTACK = frozenset({"react", "next", "next.js", "node", "frontend", "fullstack", "full-stack", "visual", "builder"})
_AI = frozenset({"ai", "ml", "machine", "learning", "gemini", "llm", "neural", "glucorelay"})


@dataclass(frozen=True)
class ResumeChoice:
    resume: Resume | None
    source: ResumeSelectionSource
    reason: str
    score: int = 0


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall((text or "").casefold()) if tok not in _STOP}


def _analysis_text(analysis: dict, title: str) -> str:
    parts = [title]
    for group in ("required", "preferred", "technologies", "responsibilities"):
        for item in analysis.get(group) or []:
            parts.append(item.get("text") or "")
    return " ".join(parts)


def infer_job_focus(analysis: dict, title: str) -> ResumeCategory:
    tokens = _tokens(_analysis_text(analysis, title))
    scores = {
        ResumeCategory.BACKEND: len(tokens & _BACKEND),
        ResumeCategory.FULLSTACK: len(tokens & _FULLSTACK),
        ResumeCategory.AI_ML: len(tokens & _AI),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return ResumeCategory.GENERAL_SWE
    return best


def _resume_tokens(resume: Resume, facts: list[CandidateFact]) -> set[str]:
    parts = [
        resume.profile_name,
        resume.profile_description,
        resume.category.value,
        " ".join(str(item) for item in (resume.focus_areas or [])),
    ]
    for fact in facts:
        parts.append(fact.fact_key)
        parts.append(str(fact.fact_value))
    return _tokens(" ".join(parts))


def score_resume(resume: Resume, facts: list[CandidateFact], analysis: dict, title: str) -> tuple[int, list[str]]:
    focus = infer_job_focus(analysis, title)
    job_tokens = _tokens(_analysis_text(analysis, title))
    resume_tokens = _resume_tokens(resume, facts)
    overlap = sorted(job_tokens & resume_tokens)
    score = len(overlap)
    reasons: list[str] = []
    if resume.category is focus:
        score += 4
        reasons.append(f"This profile is categorized as {resume.category.value.replace('_', ' ')}, which matches the role focus.")
    elif resume.category is ResumeCategory.GENERAL_SWE:
        score += 1
        reasons.append("This is a general software-engineering resume.")
    if overlap:
        reasons.append("The posting and this resume share: " + ", ".join(overlap[:8]) + ".")
    if not reasons:
        reasons.append("No specific overlap was found with this resume.")
    return score, reasons


def select_resume(
    *,
    analysis: dict,
    title: str,
    resumes: list[Resume],
    facts_by_resume: dict[int, list[CandidateFact]],
) -> ResumeChoice:
    approved = [row for row in resumes if row.is_approved and not row.is_archived]
    if not approved:
        return ResumeChoice(
            resume=None,
            source=ResumeSelectionSource.NONE,
            reason="No approved resume profiles are available. Approve a resume before CareerPilot can attach one.",
        )
    ranked: list[tuple[int, Resume, list[str]]] = []
    for resume in approved:
        score, reasons = score_resume(resume, facts_by_resume.get(resume.id, []), analysis, title)
        ranked.append((score, resume, reasons))
    ranked.sort(key=lambda item: (-item[0], not item[1].is_primary, item[1].id))
    default = next((row for row in approved if row.is_primary), approved[0])
    top_score, top, reasons = ranked[0]
    if top_score <= 1 and default is not top:
        return ResumeChoice(
            resume=default,
            source=ResumeSelectionSource.FALLBACK_DEFAULT,
            reason="No resume had a strong match, so CareerPilot used the approved default resume.",
            score=top_score,
        )
    why = f"This position emphasizes {infer_job_focus(analysis, title).value.replace('_', ' ')}. " + " ".join(reasons)
    source = ResumeSelectionSource.FALLBACK_DEFAULT if top.is_primary and top_score <= 1 else ResumeSelectionSource.AUTOMATIC
    return ResumeChoice(resume=top, source=source, reason=why, score=top_score)
