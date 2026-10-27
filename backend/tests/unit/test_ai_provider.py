"""AI provider abstraction: disabled by default, keys never leak, failures map cleanly."""

from __future__ import annotations

import httpx
import pytest

from app.ai.gemini import GeminiAnswerProvider, GeminiModelInfo, normalize_model_id, prefer_generate_model
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
        model="gemini-3.5-flash-lite",
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


def test_gemini_distinguishes_model_key_rate_limit_and_server_errors():
    secret = "super-secret-key"

    def unavailable(url, json=None, headers=None, timeout=None):
        return httpx.Response(404, text=f"models/missing not found key={secret}")

    def invalid(url, json=None, headers=None, timeout=None):
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    def server(url, json=None, headers=None, timeout=None):
        return httpx.Response(500, json={"error": {"message": "internal"}})

    cases = (
        (unavailable, "model_unavailable"),
        (invalid, "invalid_key"),
        (server, "upstream"),
    )
    for handler, kind in cases:
        provider = GeminiAnswerProvider(api_key=secret, max_retries=1, http_post=handler)
        with pytest.raises(AIProviderError) as exc:
            provider.generate(_request())
        assert exc.value.kind == kind
        assert secret not in str(exc.value)
        assert secret not in exc.value.args[0]


def test_gemini_lists_generate_content_models_without_exposing_the_key():
    def fake_get(url, headers=None, params=None, timeout=None):
        assert "key=" not in url
        assert headers["x-goog-api-key"] == "test-key"
        assert "models" in url
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.0-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.5-flash-lite",
                        "supportedGenerationMethods": ["generateContent", "countTokens"],
                    },
                    {
                        "name": "models/gemini-embedding-001",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )

    provider = GeminiAnswerProvider(api_key="test-key", http_get=fake_get)
    models = provider.list_models()
    assert [item.name for item in models] == [
        "gemini-2.0-flash",
        "gemini-3.5-flash-lite",
        "gemini-embedding-001",
    ]
    assert [item.supports_generate_content for item in models] == [True, True, False]
    assert prefer_generate_model(models, "gemini-2.5-flash") == "gemini-3.5-flash-lite"


def test_normalize_and_prefer_model_helpers():
    assert normalize_model_id("models/gemini-3.8-flash") == "gemini-3.8-flash"
    models = [
        GeminiModelInfo("gemini-3.8-flash", True, ("generateContent",)),
        GeminiModelInfo("gemini-embedding-001", False, ("embedContent",)),
    ]
    assert prefer_generate_model(models, "models/gemini-3.8-flash") == "gemini-3.8-flash"
    assert prefer_generate_model(models, "missing") == "gemini-3.8-flash"
