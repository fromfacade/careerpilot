"""List Gemini models visible to the configured API key.

Never prints the key or the raw HTTP body. Safe to run locally:

    python -m scripts.diagnose_gemini
    python -m scripts.diagnose_gemini --smoke
"""

from __future__ import annotations

import argparse
import sys

from app.ai.gemini import GeminiAnswerProvider, prefer_generate_model
from app.ai.types import GenerationRequest
from app.core.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List Gemini models for the configured key.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Send one tiny generateContent request. Does not write candidate or answer records.",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    print(f"provider={settings.ai_provider}")
    print(f"configured_model={settings.ai_model}")
    print(f"key_configured={bool(settings.gemini_api_key)}")
    if not settings.gemini_api_key:
        print("status=not_configured")
        return 1

    provider = GeminiAnswerProvider(
        api_key=settings.gemini_api_key,
        timeout_seconds=settings.ai_timeout_seconds,
        max_retries=1,
    )
    try:
        models = provider.list_models()
    except Exception as exc:
        print(f"list_status=error kind={getattr(exc, 'kind', 'unknown')}")
        print(f"list_error={exc}")
        return 1

    generate_capable = [item for item in models if item.supports_generate_content]
    print(f"models_total={len(models)}")
    print(f"generate_content_total={len(generate_capable)}")
    for item in models:
        print(f"{item.name}\tgenerateContent={item.supports_generate_content}")

    recommended = prefer_generate_model(models, settings.ai_model)
    print(f"recommended_model={recommended or 'none'}")
    configured_ok = any(item.name == settings.ai_model and item.supports_generate_content for item in models)
    print(f"configured_model_supports_generate_content={configured_ok}")

    if not args.smoke:
        return 0

    smoke_model = recommended or settings.ai_model
    print(f"smoke_model={smoke_model}")
    try:
        result = provider.generate(
            GenerationRequest(
                question="Reply with the single word ok.",
                system_instruction="Reply with one word only.",
                facts_block="(none)",
                style_block="(none)",
                temperature=0.0,
                max_output_tokens=16,
                model=smoke_model,
            )
        )
    except Exception as exc:
        print(f"smoke_status=error kind={getattr(exc, 'kind', 'unknown')}")
        print(f"smoke_error={exc}")
        return 1

    print("smoke_status=ok")
    print(f"smoke_provider={result.provider}")
    print(f"smoke_model_used={result.model}")
    print(f"smoke_text_chars={len(result.text)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
