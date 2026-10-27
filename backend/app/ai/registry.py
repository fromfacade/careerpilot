"""Resolve the configured AI provider. Default is disabled / unconfigured."""

from __future__ import annotations

from app.ai.gemini import GeminiAnswerProvider
from app.ai.mock import MockAnswerProvider
from app.ai.types import AnswerProvider
from app.core.config import Settings, get_settings
from app.core.exceptions import AIProviderError


def provider_status(settings: Settings | None = None) -> dict:
    """Public, key-free status. Safe to return to the frontend."""
    settings = settings or get_settings()
    configured = bool(settings.gemini_api_key) if settings.ai_provider == "gemini" else settings.ai_provider == "mock"
    return {
        "enabled": bool(settings.ai_enabled),
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "configured": configured,
        "available": bool(settings.ai_enabled) and configured,
    }


def get_provider(settings: Settings | None = None, *, mock: AnswerProvider | None = None) -> AnswerProvider:
    settings = settings or get_settings()
    if not settings.ai_enabled:
        raise AIProviderError("disabled", "AI generation is disabled.")
    if settings.ai_provider == "mock":
        return mock or MockAnswerProvider()
    if settings.ai_provider == "gemini":
        if not settings.gemini_api_key:
            raise AIProviderError("not_configured", "Gemini API key is not configured.")
        return GeminiAnswerProvider(
            api_key=settings.gemini_api_key,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
        )
    raise AIProviderError("not_configured", f"Unknown AI provider '{settings.ai_provider}'.")
