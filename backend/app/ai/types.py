"""Shared types for AI answer generation. No HTTP, no secrets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class GenerationRequest:
    question: str
    system_instruction: str
    facts_block: str
    style_block: str
    temperature: float
    max_output_tokens: int
    model: str


@dataclass
class GenerationResult:
    text: str
    model: str
    provider: str
    raw_usage: dict = field(default_factory=dict)


class AnswerProvider(Protocol):
    name: str

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return draft text. Must not log or return the API key."""
        ...
