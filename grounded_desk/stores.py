"""Read-only span stores. Workers do not write here."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SPAN_RE = re.compile(r"^\[(?P<id>[a-z]+-\d+)\]\s*(?P<text>.*)$")


@dataclass(frozen=True)
class Span:
    span_id: str
    text: str
    source: str


class SpanStore:
    def __init__(self, spans: list[Span]) -> None:
        self._by_id = {s.span_id: s for s in spans}

    def get(self, span_id: str) -> Span | None:
        return self._by_id.get(span_id)

    def contains(self, span_id: str) -> bool:
        return span_id in self._by_id

    def quote_matches(self, span_id: str, quote: str) -> bool:
        span = self._by_id.get(span_id)
        if span is None:
            return False
        return _norm(quote) in _norm(span.text)

    def find_quote(self, quote: str) -> Span | None:
        needle = _norm(quote)
        if not needle:
            return None
        for span in self._by_id.values():
            if needle in _norm(span.text):
                return span
        return None

    def format_block(self) -> str:
        return "\n".join(f"[{s.span_id}] {s.text}" for s in self._by_id.values())

    @property
    def span_ids(self) -> list[str]:
        return list(self._by_id)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def parse_span_file(path: Path, source: str) -> SpanStore:
    spans: list[Span] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = SPAN_RE.match(line)
        if not match:
            raise ValueError(f"{path}: expected [id] text, got {line!r}")
        spans.append(
            Span(span_id=match.group("id"), text=match.group("text"), source=source)
        )
    return SpanStore(spans)


def load_order(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
