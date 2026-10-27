"""Reject browser requests that are not from this machine's own app.

CORS alone only hides a response. This check refuses the request before
candidate data is loaded. A public website cannot send `Host: 127.0.0.1`
when it reached the process through a rebound name, and it cannot send an
allowed Origin without a preflight.
"""

from __future__ import annotations

import json

from app.core.config import get_settings

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})


def host_name(value: str) -> str:
    raw = (value or "").strip().casefold().rstrip(".")
    if raw.startswith("["):
        end = raw.find("]")
        return raw[1:end] if end > 1 else ""
    if raw.count(":") == 1:
        return raw.split(":", 1)[0]
    return raw


def local_request_allowed(host: str, origin: str | None, allowed_origins: list[str]) -> bool:
    if host_name(host) not in _LOCAL_HOSTS:
        return False
    if not origin:
        return True
    allowed = {item.strip().rstrip("/") for item in allowed_origins if item.strip()}
    return origin.strip().rstrip("/") in allowed


class LocalRequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").casefold(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        allowed = local_request_allowed(
            headers.get("host", ""),
            headers.get("origin"),
            get_settings().cors_allowed_origins_list,
        )
        if allowed:
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "CareerPilot only answers local requests from its own app."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
