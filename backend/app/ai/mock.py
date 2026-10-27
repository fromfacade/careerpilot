"""Deterministic in-process provider for tests. Makes no network calls."""

from __future__ import annotations

from app.ai.types import GenerationRequest, GenerationResult


class MockAnswerProvider:
    name = "mock"

    def __init__(self, text: str = "MOCK_DRAFT"):
        self.text = text
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        return GenerationResult(text=self.text, model=request.model, provider=self.name)
