"""Shared secret for opening a browser from this machine.

Host and Origin checks still apply. They do not stop another local program
from calling the API, so browser sessions also require this token. The token
is created on first use and kept in gitignored storage. It is not logged.
"""

from __future__ import annotations

import hmac
import secrets
from pathlib import Path

from app.core.config import get_settings


def token_path() -> Path:
    root = Path(get_settings().resume_storage_dir).parent
    return root / "local-api-token"


def load_or_create_token() -> str:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        current = path.read_text(encoding="utf-8").strip()
        if current:
            return current
    generated = secrets.token_urlsafe(32)
    path.write_text(generated, encoding="utf-8")
    return generated


def token_matches(provided: str | None) -> bool:
    expected = load_or_create_token()
    offered = (provided or "").strip()
    if not offered:
        return False
    return hmac.compare_digest(offered, expected)
