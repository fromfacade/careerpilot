"""One-off style comparison using synthetic facts. Writes no candidate records.

    python -m scripts.evaluate_writing_style
"""

from __future__ import annotations

from app.ai.registry import get_provider
from app.ai.types import GenerationRequest
from app.core.config import Settings
from app.services.generation_service import _SYSTEM
from app.services.writing_style_service import DEFAULT_INSTRUCTIONS, DEFAULT_PHRASES_TO_AVOID, format_profile_guidance
from app.models.writing_style import WritingStyleProfile
from app.models.enums import (
    WritingComplexity,
    WritingFormality,
    WritingLength,
    WritingTechnicalDetail,
    WritingTone,
    WritingVocabulary,
)

QUESTION = "Describe a challenging technical problem you solved."
FACTS = '- [project] Alpha Queue: {"name": "Alpha Queue", "technologies": ["FastAPI", "Redis"], "bullets": ["Processed jobs in parallel and retried failures."]}'
GENERIC_SYSTEM = (
    "Write a polished professional job-application answer using the facts. "
    "Be impressive and conclude with personal growth."
)


def _mentions(text: str) -> dict[str, bool]:
    lowered = text.casefold()
    return {
        "uses_alpha_queue": "alpha queue" in lowered or "fastapi" in lowered,
        "invents_nasa": "nasa" in lowered,
        "uses_avoided_phrase": any(phrase in lowered for phrase in DEFAULT_PHRASES_TO_AVOID),
    }


def main() -> int:
    settings = Settings()
    print(f"ai_enabled={settings.ai_enabled} key_configured={bool(settings.gemini_api_key)}")
    if not settings.ai_enabled or not settings.gemini_api_key:
        print("status=skipped")
        return 0
    provider = get_provider(settings)
    generic = provider.generate(
        GenerationRequest(
            question=QUESTION,
            system_instruction=GENERIC_SYSTEM,
            facts_block=FACTS,
            style_block="(none)",
            temperature=0.4,
            max_output_tokens=220,
            model=settings.ai_model,
        )
    )
    profile = WritingStyleProfile(
        candidate_id=0,
        tone=WritingTone.PROFESSIONAL_CONVERSATIONAL,
        formality=WritingFormality.MEDIUM,
        preferred_length=WritingLength.SHORT_MEDIUM,
        sentence_complexity=WritingComplexity.MODERATE,
        technical_detail=WritingTechnicalDetail.SPECIFIC,
        vocabulary=WritingVocabulary.STRAIGHTFORWARD,
        phrases_to_avoid=list(DEFAULT_PHRASES_TO_AVOID),
        additional_instructions=DEFAULT_INSTRUCTIONS,
    )
    personalized = provider.generate(
        GenerationRequest(
            question=QUESTION,
            system_instruction=_SYSTEM,
            facts_block=FACTS,
            style_block="(none)",
            style_guidance=format_profile_guidance(profile),
            writing_samples_block=(
                "<<<WRITING_SAMPLE id=1 category=technical_experience origin=user_written>>>\n"
                "I built a FastAPI worker that retried failed Redis jobs instead of dropping them.\n"
                "<<<END_WRITING_SAMPLE>>>"
            ),
            temperature=0.4,
            max_output_tokens=220,
            model=settings.ai_model,
        )
    )
    print("generic_chars=", len(generic.text))
    print("personalized_chars=", len(personalized.text))
    print("generic_signals=", _mentions(generic.text))
    print("personalized_signals=", _mentions(personalized.text))
    print("generic_excerpt=", generic.text[:180].replace("\n", " "))
    print("personalized_excerpt=", personalized.text[:180].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
