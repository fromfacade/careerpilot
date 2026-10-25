"""Structured logging configuration.

Logs are emitted as single-line JSON so they are easy to grep, pipe into a
log aggregator later, and never accidentally leak multi-line stack traces
that break line-based parsing. PII (resume contents, full job descriptions,
credentials) must never be passed into log fields — only IDs, counts, and
status strings.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers if configure_logging is called more than once
    # (e.g. once by the app factory, once by a test fixture).
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers at DEBUG while keeping INFO+ visible.
    logging.getLogger("httpx").setLevel(max(logging.INFO, root.level))
    logging.getLogger("apscheduler").setLevel(max(logging.INFO, root.level))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(**fields: Any) -> dict[str, dict[str, Any]]:
    """Helper to attach structured fields: logger.info("msg", extra=log_extra(job_id=1))."""
    return {"extra_fields": fields}
