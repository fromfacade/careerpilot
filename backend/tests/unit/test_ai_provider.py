"""AI provider abstraction: disabled by default, keys never leak, failures map cleanly."""

from __future__ import annotations

import httpx
import pytest

from app.ai.gemini import GeminiAnswerProvider
from app.ai.registry import get_provider, provider_status
from app.ai.types import GenerationRequest
from app.core.config import Settings
from app.core.exceptions import AIProviderError


def _request() -> GenerationRequest:
    return GenerationRequest(
        question="Why this role?",
        system_instruction="Be honest.",
        facts_block="- Built Alpha.",
        style_block="",
        temperature=0.2,
        max_output_tokens=100,
        model="gemini-2.0-flash",
    )


def test_status_is_disabled_and_key_free_by_default():
    status = provider_status(Settings(ai_enabled=False, gemini_api_key="secret-should-not-appear"))
    assert status["enabled"] is False
    assert status["available"] is False
    assert status["configured"] is True
    dumped = str(status)
    assert "secret-should-not-appear" not in dumped
    assert "gemini_api_key" not in dumped


def test_get_provider_raises_when_disabled():
    with pytest.raises(AIProviderError) as exc:
        get_provider(Settings(ai_enabled=False, gemini_api_key="x"))
    assert exc.value.kind == "disabled"


def test_get_provider_raises_when_gemini_key_missing():
    with pytest.raises(AIProviderError) as exc:
        get_provider(Settings(ai_enabled=True, ai_provider="gemini", gemini_api_key=""))
    assert exc.value.kind == "not_configured"


def test_gemini_parses_a_successful_response():
    def fake_post(url, json=None, headers=None, timeout=None):
        assert "key=" not in url
        assert headers["x-goog-api-key"] == "test-key"
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Because I build backends."}]}}], "usageMetadata": {"totalTokenCount": 9}},
        )

    provider = GeminiAnswerProvider(api_key="test-key", http_post=fake_post)
    result = provider.generate(_request())
    assert result.text == "Because I build backends."
    assert result.provider == "gemini"
    assert "test-key" not in result.text


def test_gemini_timeout_and_rate_limit_do_not_include_the_key():
    def timeout_post(url, json=None, headers=None, timeout=None):
        raise httpx.TimeoutException("timed out talking to host")

    provider = GeminiAnswerProvider(api_key="super-secret-key", max_retries=1, http_post=timeout_post)
    with pytest.raises(AIProviderError) as exc:
        provider.generate(_request())
    assert exc.value.kind == "timeout"
    assert "super-secret-key" not in str(exc.value)

    def limited_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(429, json={"error": {"message": "quota"}})

    limited = GeminiAnswerProvider(api_key="super-secret-key", max_retries=1, http_post=limited_post)
    with pytest.raises(AIProviderError) as exc:
        limited.generate(_request())
    assert exc.value.kind == "rate_limited"
    assert "super-secret-key" not in str(exc.value)


def test_gemini_rejects_empty_candidates():
    def empty_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(200, json={"candidates": []})

    provider = GeminiAnswerProvider(api_key="k", http_post=empty_post)
    with pytest.raises(AIProviderError) as exc:
        provider.generate(_request())
    assert exc.value.kind == "upstream"
