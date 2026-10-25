"""Shared exception types used by services and translated to HTTP errors in routers.

Keeping these in core (rather than per-module) lets routers catch a small,
well-known set of exception types without importing every service module.
"""

from __future__ import annotations


class CareerPilotError(Exception):
    """Base class for all expected, handled application errors."""


class NotFoundError(CareerPilotError):
    """Raised when a requested entity does not exist."""


class ConflictError(CareerPilotError):
    """Raised when an operation conflicts with current state (e.g. duplicate, already running)."""


class ValidationError(CareerPilotError):
    """Raised for business-rule validation failures not already caught by Pydantic."""


class JobSourceFetchError(CareerPilotError):
    """Raised by job source adapters when a fetch ultimately fails after retries.

    Carries enough context for the discovery service to record a per-source
    failure without crashing the whole discovery run.
    """

    def __init__(self, provider: str, board_token: str, message: str):
        self.provider = provider
        self.board_token = board_token
        super().__init__(f"[{provider}:{board_token}] {message}")
