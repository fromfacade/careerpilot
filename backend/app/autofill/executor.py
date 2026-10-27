"""Boundary for a future headed browser. Nothing here launches one.

Planning stays in `mapping` and `materials`. A later increment can provide
a Playwright executor behind `FormExecutor`. This increment always returns
an executor that refuses to fill or attach.
"""

from __future__ import annotations

from typing import Protocol


class BrowserFillUnavailable(RuntimeError):
    """Raised when something tries to drive a browser before that increment exists."""


class FormExecutor(Protocol):
    def fill_text(self, field_id: str, value: str) -> None:
        """Type into one field the user has already approved."""

    def attach_file(self, field_id: str, filename: str, content: bytes) -> None:
        """Attach bytes the planner already selected. The filename is a display name, not a storage path."""


class UnavailableFormExecutor:
    def fill_text(self, field_id: str, value: str) -> None:
        raise BrowserFillUnavailable(
            "Browser filling is not enabled. Review the plan, then submit on the employer site."
        )

    def attach_file(self, field_id: str, filename: str, content: bytes) -> None:
        raise BrowserFillUnavailable(
            "Resume attachment in a browser is not enabled. The plan only names the selected file."
        )


def form_executor() -> FormExecutor:
    return UnavailableFormExecutor()
