"""Deterministic, offline resume parsing (Phase 2.1).

Nothing in this subpackage makes a network call or imports an AI provider
client -- resume content never leaves this machine during upload/parsing.
AI-assisted analysis (Phase 2.2+) is a separate, explicitly-configured path
that does not exist yet.
"""
