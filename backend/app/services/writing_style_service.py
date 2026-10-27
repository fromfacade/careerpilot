"""Writing style preferences. One profile per candidate; defaults match
the candidate's stated voice until they edit them.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.candidate import Candidate
from app.models.enums import (
    WritingComplexity,
    WritingFormality,
    WritingLength,
    WritingTechnicalDetail,
    WritingTone,
    WritingVocabulary,
)
from app.models.writing_style import WritingStyleProfile

DEFAULT_PHRASES_TO_AVOID = [
    "leverage",
    "synergy",
    "robust",
    "passionate about",
    "thrilled",
    "honed my skills",
    "this experience strengthened",
    "in today's fast-paced",
    "hit the ground running",
    "think outside the box",
    "results-driven",
    "utilize",
]

DEFAULT_INSTRUCTIONS = (
    "Write professionally but conversationally. Use straightforward vocabulary "
    "and short-to-medium sentences. Give specific technical explanations. Use "
    "natural transitions. Skip unnecessary introductions and generic concluding "
    "statements about personal growth. Do not exaggerate accomplishments. Avoid "
    "corporate buzzwords and overly polished language."
)


def _clean_phrases(phrases: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in phrases:
        phrase = " ".join(str(raw).split()).strip()
        if not phrase:
            continue
        if len(phrase) > 80:
            raise ValidationError("Each phrase to avoid must be 80 characters or fewer.")
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(phrase)
    return cleaned


def get_or_create_profile(db: Session, candidate: Candidate) -> WritingStyleProfile:
    profile = db.execute(
        select(WritingStyleProfile).where(WritingStyleProfile.candidate_id == candidate.id)
    ).scalar_one_or_none()
    if profile is not None:
        return profile
    profile = WritingStyleProfile(
        candidate_id=candidate.id,
        tone=WritingTone.PROFESSIONAL_CONVERSATIONAL,
        formality=WritingFormality.MEDIUM,
        preferred_length=WritingLength.SHORT_MEDIUM,
        sentence_complexity=WritingComplexity.MODERATE,
        technical_detail=WritingTechnicalDetail.SPECIFIC,
        vocabulary=WritingVocabulary.STRAIGHTFORWARD,
        phrases_to_avoid=list(DEFAULT_PHRASES_TO_AVOID),
        additional_instructions=DEFAULT_INSTRUCTIONS,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    candidate: Candidate,
    *,
    tone: WritingTone | None = None,
    formality: WritingFormality | None = None,
    preferred_length: WritingLength | None = None,
    sentence_complexity: WritingComplexity | None = None,
    technical_detail: WritingTechnicalDetail | None = None,
    vocabulary: WritingVocabulary | None = None,
    phrases_to_avoid: list[str] | None = None,
    additional_instructions: str | None = None,
) -> WritingStyleProfile:
    profile = get_or_create_profile(db, candidate)
    if tone is not None:
        profile.tone = tone
    if formality is not None:
        profile.formality = formality
    if preferred_length is not None:
        profile.preferred_length = preferred_length
    if sentence_complexity is not None:
        profile.sentence_complexity = sentence_complexity
    if technical_detail is not None:
        profile.technical_detail = technical_detail
    if vocabulary is not None:
        profile.vocabulary = vocabulary
    if phrases_to_avoid is not None:
        profile.phrases_to_avoid = _clean_phrases(phrases_to_avoid)
    if additional_instructions is not None:
        profile.additional_instructions = additional_instructions.strip()
    db.commit()
    db.refresh(profile)
    return profile


def format_profile_guidance(profile: WritingStyleProfile) -> str:
    avoid = ", ".join(profile.phrases_to_avoid) if profile.phrases_to_avoid else "(none)"
    extra = profile.additional_instructions.strip() or "(none)"
    return (
        f"Tone: {profile.tone.value}. Formality: {profile.formality.value}. "
        f"Length: {profile.preferred_length.value}. Sentence complexity: "
        f"{profile.sentence_complexity.value}. Technical detail: "
        f"{profile.technical_detail.value}. Vocabulary: {profile.vocabulary.value}. "
        f"Phrases to avoid: {avoid}. Additional instructions: {extra}"
    )
