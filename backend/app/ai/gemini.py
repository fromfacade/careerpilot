"""Gemini generateContent adapter.

Uses httpx (already a project dependency) so we do not add a vendor SDK.
The API key is sent only as the `x-goog-api-key` header and is never
included in log fields, exception messages, or return values.
"""

from __future__ import annotations

import time

import httpx

from app.ai.types import GenerationRequest, GenerationResult
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRYABLE = {429, 500, 502, 503, 504}


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


class GeminiAnswerProvider:
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        http_post=None,
    ):
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http_post = http_post or httpx.post

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self._api_key:
            raise AIProviderError("not_configured", "Gemini API key is not configured.")
        url = _GEMINI_URL.format(model=request.model)
        payload = {
            "systemInstruction": {"parts": [{"text": request.system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"Question:\n{request.question}\n\nVerified facts:\n{request.facts_block}\n\nStyle references:\n{request.style_block}"}
                    ],
                }
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
            },
        }
        headers = {"x-goog-api-key": self._api_key, "content-type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._http_post(url, json=payload, headers=headers, timeout=self._timeout)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("ai_provider_timeout", extra=log_extra(provider="gemini", attempt=attempt))
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "ai_provider_transport_error",
                    extra=log_extra(provider="gemini", attempt=attempt, error=_redact(str(exc), self._api_key)),
                )
            else:
                if response.status_code == 200:
                    return self._parse(response.json(), request.model)
                if response.status_code == 401 or response.status_code == 403:
                    raise AIProviderError("not_configured", "Gemini rejected the configured API key.")
                if response.status_code in _RETRYABLE and attempt < self._max_retries:
                    time.sleep(0.2 * attempt)
                    continue
                if response.status_code == 429:
                    raise AIProviderError("rate_limited", "Gemini rate-limited the request.")
                raise AIProviderError(
                    "upstream",
                    f"Gemini returned HTTP {response.status_code}.",
                )
        raise AIProviderError("timeout", f"Gemini request failed after {self._max_retries} attempts: {last_error}")

    def _parse(self, body: object, model: str) -> GenerationResult:
        if not isinstance(body, dict):
            raise AIProviderError("upstream", "Gemini returned a non-object body.")
        candidates = body.get("candidates") or []
        if not candidates:
            raise AIProviderError("upstream", "Gemini returned no candidates.")
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise AIProviderError("upstream", "Gemini returned empty text.")
        usage = body.get("usageMetadata") if isinstance(body.get("usageMetadata"), dict) else {}
        return GenerationResult(text=text, model=model, provider=self.name, raw_usage=usage)
