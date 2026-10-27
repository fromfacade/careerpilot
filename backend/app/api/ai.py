"""AI status only. Generation is a later increment. Never returns secrets."""

from __future__ import annotations

from fastapi import APIRouter

from app.ai.registry import provider_status

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def read_ai_status():
    status = provider_status()
    # Belt-and-suspenders: refuse to serialize anything that looks like a key.
    assert "gemini_api_key" not in status
    assert "api_key" not in status
    return status
