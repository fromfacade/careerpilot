"""Greenhouse receipt and failure phrases.

A button click, a redirect, and an HTTP status are not inputs here.
Only visible page text can establish an outcome. Script and style
contents are ignored. Both a receipt and an error means the outcome
is still unknown.
"""

from __future__ import annotations

import json
import re

RECEIVED_PHRASES = (
    "thank you for applying",
    "thanks for applying",
    "thank you for your application",
    "application has been submitted",
    "application was submitted",
    "application has been received",
    "application was received",
    "we have received your application",
    "we've received your application",
    "we received your application",
    "your application has been received",
    "your application was submitted",
    "your application has been successfully submitted",
    "successfully submitted your application",
    "your application is complete",
    "you have already applied",
    "you've already applied",
    "you already applied",
)

FAILURE_PHRASES = (
    "there was a problem submitting",
    "there was an error submitting your application",
    "could not submit your application",
    "your application could not be submitted",
    "please fix the errors",
    "please correct the following errors",
    "this field is required",
    "submission failed",
    "unable to submit",
)

_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    text = _TAG.sub(" ", _STYLE.sub(" ", _SCRIPT.sub(" ", html or "")))
    return " ".join(text.casefold().split())


def classify_confirmation(html: str) -> str | None:
    """Return 'received', 'failed', or None. None preserves confirmation_unknown."""
    text = visible_text(html)
    received = any(phrase in text for phrase in RECEIVED_PHRASES)
    failed = any(phrase in text for phrase in FAILURE_PHRASES)
    if received and failed:
        return None
    if received:
        return "received"
    if failed:
        return "failed"
    return None


def outcome_wait_js() -> str:
    phrases = list(RECEIVED_PHRASES) + list(FAILURE_PHRASES)
    encoded = ", ".join(json.dumps(phrase) for phrase in phrases)
    return f"""() => {{
  const text = (document.body && document.body.innerText || '').toLowerCase();
  const phrases = [{encoded}];
  return phrases.some((phrase) => text.includes(phrase));
}}"""
