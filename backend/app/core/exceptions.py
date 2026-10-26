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


class UnsupportedFileFormatError(CareerPilotError):
    """Raised at the API boundary when an uploaded file's extension/content
    type isn't one of the explicitly supported resume formats. Mapped to
    HTTP 415 -- the file is rejected before anything is written to disk."""


class FileTooLargeError(CareerPilotError):
    """Raised when an uploaded file exceeds `settings.resume_max_upload_mb`.
    Mapped to HTTP 413, checked before writing anything to disk."""


class ResumeExtractionError(CareerPilotError):
    """Raised by app/resume_parsing/extractors.py when text cannot be
    pulled from an otherwise-correctly-formatted file (corrupt/encrypted/
    empty PDF or DOCX). Caught by resume_service, which still persists the
    original upload with parse_status=FAILED -- a parse failure must never
    lose the file (immutability requirement) or crash the request."""


class JobSourceFetchError(CareerPilotError):
    """Raised by job source adapters when a fetch ultimately fails after retries.

    Carries enough context for the discovery service to record a per-source
    failure without crashing the whole discovery run.
    """

    def __init__(self, provider: str, board_token: str, message: str):
        self.provider = provider
        self.board_token = board_token
        super().__init__(f"[{provider}:{board_token}] {message}")
