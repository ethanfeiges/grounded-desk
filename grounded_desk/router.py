"""Keyword router. Swap this function for an LLM later; keep the output a path id."""

from __future__ import annotations

from grounded_desk.models import PathName

_REFUND = ("refund", "return", "refund window", "changed my mind")
_BUG = ("crash", "bug", "version", "file this")
_HOWTO = ("how do i", "reset", "password", "where is")


def classify(email_text: str) -> PathName:
    text = email_text.lower()
    if any(k in text for k in _REFUND):
        return "refund"
    if any(k in text for k in _BUG):
        return "bug"
    if any(k in text for k in _HOWTO):
        return "how_to"
    return "how_to"
