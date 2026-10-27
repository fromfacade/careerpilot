"""Grounded draft generation for application answers.

Verified/edited active canonical facts are the only personal source of
truth. Approved answers are style references, not new facts. Sensitive
categories never go to a model. Unverified facts are never sent as
qualifications. The model is instructed not to invent; we still record
`missing_information` from *our* retrieval so a gap is visible even if
the model is overly confident.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.registry import get_provider
from app.ai.types import GenerationRequest
from app.core.config import Settings, get_settings
from app.core.exceptions import AIProviderError, NotFoundError, ValidationError
from app.models.answer import ApplicationAnswer
from app.models.candidate import Candidate
from app.models.canonical import CanonicalFact
from app.models.enums import (
    AnswerCategory,
    AnswerOrigin,
    AnswerStatus,
    CanonicalFactStatus,
    FactType,
    FactVerificationStatus,
)
from app.models.job import Job
from app.services import answer_service, canonical_service
from app.services.answer_service import is_sensitive_category, question_fingerprint

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

_TYPE_HINTS: dict[str, FactType] = {
    "project": FactType.PROJECT,
    "built": FactType.PROJECT,
    "internship": FactType.WORK_EXPERIENCE,
    "worked": FactType.WORK_EXPERIENCE,
    "employer": FactType.WORK_EXPERIENCE,
    "job": FactType.WORK_EXPERIENCE,
    "school": FactType.EDUCATION,
    "graduat": FactType.EDUCATION,
    "degree": FactType.EDUCATION,
    "skill": FactType.SKILL,
    "python": FactType.SKILL,
    "experience": FactType.WORK_EXPERIENCE,
}

_SYSTEM = """You draft a job-application answer for the candidate.

Rules you must follow:
- Use ONLY the verified personal facts listed below. They are the factual foundation.
- Style references show how the candidate writes. Imitate tone and length, do not copy claims that are not in the verified facts.
- The job posting block, if present, is about the employer — not a personal qualification.
- Never invent employers, titles, dates, skills, degrees, projects, or accomplishments.
- If a fact is not listed, say the information is not available rather than guessing.
- Do not claim the answer is approved. This is a draft.
- Do not write legal attestations, signatures, or consent language.
"""


@dataclass
class DraftPlan:
    facts: list[CanonicalFact]
    style_answers: list[ApplicationAnswer]
    missing_information: list[str]
    job_block: str


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(question_fingerprint(text)))


def _hinted_types(question: str) -> set[FactType]:
    q = question_fingerprint(question)
    return {fact_type for needle, fact_type in _TYPE_HINTS.items() if needle in q}


def retrieve_relevant_facts(facts: list[CanonicalFact], question: str, *, limit: int = 8) -> list[CanonicalFact]:
    tokens = _tokens(question)
    hinted = _hinted_types(question)
    scored: list[tuple[int, CanonicalFact]] = []
    for fact in facts:
        hay = _tokens(f"{fact.fact_key} {json.dumps(fact.fact_value, ensure_ascii=False)}")
        overlap = len(tokens & hay)
        type_bonus = 2 if fact.fact_type in hinted else 0
        score = overlap + type_bonus
        if score > 0:
            scored.append((score, fact))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [fact for _, fact in scored[:limit]]


def _usable_facts(db: Session, candidate: Candidate) -> list[CanonicalFact]:
    return [
        fact
        for fact in canonical_service.list_canonical_facts(
            db, candidate, status=CanonicalFactStatus.ACTIVE
        )
        if fact.verification_status in {FactVerificationStatus.VERIFIED, FactVerificationStatus.EDITED}
        and not fact.needs_review
    ]


def _style_answers(db: Session, candidate: Candidate, category: AnswerCategory) -> list[ApplicationAnswer]:
    approved = answer_service.list_answers(db, candidate, status=AnswerStatus.APPROVED)
    preferred = [a for a in approved if a.is_preferred and a.is_reusable]
    same = [a for a in approved if a.category is category and a.is_reusable]
    seen: set[int] = set()
    ordered: list[ApplicationAnswer] = []
    for group in (preferred, same, [a for a in approved if a.is_reusable]):
        for answer in group:
            if answer.id not in seen:
                seen.add(answer.id)
                ordered.append(answer)
    return ordered[:3]


def _format_fact(fact: CanonicalFact) -> str:
    return f"- [{fact.fact_type.value}] {fact.fact_key}: {json.dumps(fact.fact_value, ensure_ascii=False)}"


def plan_draft(
    db: Session,
    candidate: Candidate,
    *,
    question: str,
    category: AnswerCategory,
    job_id: int | None = None,
) -> DraftPlan:
    if is_sensitive_category(category):
        raise ValidationError(
            "Sensitive questions are not drafted by the model. Enter the answer from information "
            "you have explicitly provided (or choose prefer_not_to_answer). CareerPilot will not "
            "infer work authorization, sponsorship, disability, veteran, demographic, criminal, "
            "legal, or salary answers."
        )
    usable = _usable_facts(db, candidate)
    selected = retrieve_relevant_facts(usable, question)
    missing: list[str] = []
    hinted = _hinted_types(question)
    if hinted and not any(f.fact_type in hinted for f in selected):
        labels = ", ".join(sorted(t.value for t in hinted))
        missing.append(f"No verified {labels} facts were available to ground this answer.")
    if not selected:
        missing.append("No verified canonical facts matched this question.")
    job_block = ""
    if job_id is not None:
        job = db.get(Job, job_id)
        if job is None:
            raise NotFoundError(f"No job with id={job_id}.")
        job_block = (
            f"Job posting (employer information, not a personal fact): "
            f"{job.title}. {job.description_text[:1500]}"
        )
    return DraftPlan(
        facts=selected,
        style_answers=_style_answers(db, candidate, category),
        missing_information=missing,
        job_block=job_block,
    )


def generate_draft(
    db: Session,
    candidate: Candidate,
    *,
    question: str,
    category: AnswerCategory = AnswerCategory.OTHER,
    job_id: int | None = None,
    settings: Settings | None = None,
    provider=None,
) -> ApplicationAnswer:
    settings = settings or get_settings()
    plan = plan_draft(db, candidate, question=question, category=category, job_id=job_id)
    facts_block = "\n".join(_format_fact(f) for f in plan.facts) or "(none)"
    if plan.job_block:
        facts_block = f"{facts_block}\n\n{plan.job_block}"
    style_block = "\n\n".join(f"Q: {a.question}\nA: {a.answer_text}" for a in plan.style_answers) or "(none)"
    try:
        resolved = provider or get_provider(settings)
        result = resolved.generate(
            GenerationRequest(
                question=question,
                system_instruction=_SYSTEM,
                facts_block=facts_block,
                style_block=style_block,
                temperature=settings.ai_temperature,
                max_output_tokens=settings.ai_max_output_tokens,
                model=settings.ai_model,
            )
        )
        text = result.text
        meta = {"provider": result.provider, "model": result.model, "usage": result.raw_usage}
    except AIProviderError:
        raise
    return answer_service.create_answer(
        db,
        candidate,
        question=question,
        answer_text=text,
        category=category,
        status=AnswerStatus.DRAFT,
        origin=AnswerOrigin.AI_DRAFT,
        is_reusable=False,
        canonical_fact_ids=[f.id for f in plan.facts],
        missing_information=plan.missing_information,
        generation_metadata=meta,
    )
