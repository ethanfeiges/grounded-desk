"""Thread-scoped run state. Not the policy store."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from grounded_desk.paths import ROOT

DEFAULT_DB = ROOT / ".data" / "tickets.sqlite"


def sqlite_saver(path: Path | None = None) -> SqliteSaver:
    db = path or DEFAULT_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, check_same_thread=False)
    return SqliteSaver(conn)


def thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def pending_nodes(graph: Any, thread_id: str) -> list[str]:
    snap = graph.get_state(thread_config(thread_id))
    return list(snap.next)


def interrupt_payloads(result: dict[str, Any]) -> list[Any]:
    raw = result.get("__interrupt__") or ()
    out: list[Any] = []
    for item in raw:
        value = getattr(item, "value", item)
        out.append(value)
    return out
