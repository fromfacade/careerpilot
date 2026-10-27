"""AI provider adapters. Disabled by default; no keys leave this package."""

from app.ai.registry import get_provider, provider_status

__all__ = ["get_provider", "provider_status"]
