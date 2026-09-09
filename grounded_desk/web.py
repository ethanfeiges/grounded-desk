"""Localhost desk UI. Streams one ticket through the compiled graph."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from grounded_desk.answers import public_items
from grounded_desk.checkpointing import pending_nodes, thread_config
from grounded_desk.graph import get_app_graph, ticket_input
from grounded_desk.paths import EMAILS
from grounded_desk.router import classify
from grounded_desk.tickets import load_bundle
from grounded_desk.workers import make_worker, resolve_api_key, resolve_cursor_api_key
from langgraph.types import Command

STATIC = Path(__file__).resolve().parent / "static"

TICKET_BLURBS = {
    "refund_day20": "Lamp, day 20, order on file. Refund path; pauses for approval.",
    "refund_day12": "Headphones, day 12, order on file. Same refund walk, still inside the window.",
    "missing_order": "Asks for ORD-9999, which is not on disk. Spawns lookup_order.",
    "howto_password": "Password reset. How-to path; no approval pause.",
    "bug_crash": "iOS crash report. Bug path; no approval pause.",
}

app = FastAPI(title="Grounded Desk", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class RunBody(BaseModel):
    ticket_id: str
    condition: Literal["clean", "noisy"] = "clean"
    backend: Literal["openai", "cursor", "demo"] = "demo"
    model: str | None = None
    thread_id: str | None = None
    skip_approval: bool = False


class ResumeBody(BaseModel):
    thread_id: str
    approved: bool = True
    backend: Literal["openai", "cursor", "demo"] = "demo"
    model: str | None = None
    skip_approval: bool = False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "openai": bool(resolve_api_key()),
        "cursor": bool(resolve_cursor_api_key()),
        "demo": True,
    }


@app.get("/api/tickets")
def list_tickets() -> dict[str, Any]:
    tickets = []
    for path in sorted(EMAILS.glob("*.txt")):
        ticket_id = path.stem
        bundle = load_bundle(ticket_id)
        tickets.append(
            {
                "ticket_id": ticket_id,
                "path": classify(bundle.email_block),
                "blurb": TICKET_BLURBS.get(ticket_id, ""),
                "email": bundle.email_block,
            }
        )
    return {"tickets": tickets}


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: str) -> dict[str, Any]:
    if not (EMAILS / f"{ticket_id}.txt").exists():
        raise HTTPException(404, f"unknown ticket {ticket_id}")
    bundle = load_bundle(ticket_id)
    return {
        "ticket_id": ticket_id,
        "path": classify(bundle.email_block),
        "email": bundle.email_block,
        "policy": bundle.policy.format_block(),
        "decoy": bundle.decoy.format_block(),
        "extract": [item.model_dump() for item in public_items(ticket_id, "extract")],
        "playbook": [item.model_dump() for item in public_items(ticket_id, "playbook")],
    }


@app.get("/api/threads/{thread_id}")
def thread_status(
    thread_id: str,
    backend: Literal["openai", "cursor", "demo"] = "demo",
    model: str | None = None,
    skip_approval: bool = False,
) -> dict[str, Any]:
    graph = _graph(backend, model, skip_approval)
    return snapshot_view(graph, thread_id)


@app.post("/api/run")
def run_ticket(body: RunBody) -> StreamingResponse:
    if not (EMAILS / f"{body.ticket_id}.txt").exists():
        raise HTTPException(404, f"unknown ticket {body.ticket_id}")
    thread_id = body.thread_id or body.ticket_id
    graph = _graph(body.backend, body.model, body.skip_approval)
    payload = ticket_input(body.ticket_id, condition=body.condition)
    return StreamingResponse(
        _stream(graph, payload, thread_id, start_meta=body.model_dump()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/resume")
def resume_ticket(body: ResumeBody) -> StreamingResponse:
    graph = _graph(body.backend, body.model, body.skip_approval)
    payload = Command(resume="approve" if body.approved else "reject")
    return StreamingResponse(
        _stream(graph, payload, body.thread_id, start_meta=body.model_dump()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _graph(backend: str, model: str | None, skip_approval: bool) -> Any:
    return get_app_graph(
        make_worker(backend, model),
        interrupt_refunds=not skip_approval,
    )


def _stream(
    graph: Any,
    payload: Any,
    thread_id: str,
    *,
    start_meta: dict[str, Any],
) -> Iterator[str]:
    yield _sse("start", {"thread_id": thread_id, **start_meta})
    try:
        for chunk in graph.stream(payload, thread_config(thread_id), stream_mode="updates"):
            if not isinstance(chunk, dict):
                yield _sse("node", {"raw": chunk})
                continue
            for name, update in chunk.items():
                yield _sse("node", {"node": name, "update": _jsonable(update)})
    except Exception as exc:
        if "Interrupt" in type(exc).__name__:
            yield _sse("done", snapshot_view(graph, thread_id))
            return
        yield _sse("error", {"message": str(exc)})
        return
    yield _sse("done", snapshot_view(graph, thread_id))


def snapshot_view(graph: Any, thread_id: str) -> dict[str, Any]:
    snap = graph.get_state(thread_config(thread_id))
    values = _jsonable(dict(snap.values) if snap.values else {})
    interrupts: list[Any] = []
    for task in getattr(snap, "tasks", ()) or ():
        for item in getattr(task, "interrupts", ()) or ():
            interrupts.append(_jsonable(getattr(item, "value", item)))
    nxt = list(snap.next)
    return {
        "thread_id": thread_id,
        "next": nxt,
        "values": values,
        "interrupts": interrupts,
        "paused": bool(interrupts) or nxt == ["approve"],
        "pending": pending_nodes(graph, thread_id),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Open the grounded desk UI on localhost.")
    parser.add_argument("--host", default=os.environ.get("GROUNDED_DESK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("GROUNDED_DESK_PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    import uvicorn

    print(f"Grounded Desk UI -> http://{args.host}:{args.port}")
    uvicorn.run("grounded_desk.web:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
