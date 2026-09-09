"""Compiled desk graph.

Control plane is this file: edges, the keyword router, and the gather
conditional. extract and playbook are live LangChain workers. verify is a
code unit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from grounded_desk.answers import load_answers, public_items
from grounded_desk.checkpointing import sqlite_saver, thread_config
from grounded_desk.models import Claim
from grounded_desk.router import classify
from grounded_desk.score import task_scores
from grounded_desk.state import DeskState
from grounded_desk.tickets import find_order_id, load_bundle, order_on_disk
from grounded_desk.verify import verify_claims
from grounded_desk.workers import DeskWorker, live_worker


def _run_worker(worker: DeskWorker, task: str, state: DeskState) -> list[Claim]:
    return worker.complete(
        task,
        state["ticket_id"],
        email_block=state["email_text"],
        policy_block=state.get("policy_prompt") or "",
        path=state.get("path") or "",
        items=public_items(state["ticket_id"], task),
    )


def build_graph(
    worker: DeskWorker | None = None,
    *,
    checkpointer: Any | None = None,
    interrupt_refunds: bool = True,
) -> Any:
    worker = worker or live_worker()

    def route(state: DeskState) -> dict[str, str]:
        return {"path": classify(state["email_text"])}

    def extract(state: DeskState) -> dict[str, Any]:
        claims = [c.model_dump() for c in _run_worker(worker, "extract", state)]
        return {"claims": claims}

    def playbook(state: DeskState) -> dict[str, Any]:
        claims = [c.model_dump() for c in _run_worker(worker, "playbook", state)]
        return {"claims": claims}

    def gather(state: DeskState) -> dict[str, Any]:
        order_id = find_order_id(state["email_text"])
        return {"order_id": order_id}

    def after_gather(state: DeskState) -> list[Send] | str:
        order_id = state.get("order_id")
        if (
            order_id
            and order_on_disk(order_id) is None
            and not state.get("order_record")
        ):
            return [
                Send(
                    "lookup_order",
                    {
                        "ticket_id": state["ticket_id"],
                        "order_id": order_id,
                        "email_text": state["email_text"],
                        "claims": state.get("claims") or [],
                    },
                )
            ]
        return "verify"

    def lookup_order(state: DeskState) -> dict[str, Any]:
        order_id = state["order_id"]
        record = order_on_disk(order_id) or {
            "order_id": order_id,
            "found": False,
        }
        return {"order_record": record, "lookup_ran": True}

    def verify(state: DeskState) -> dict[str, Any]:
        bundle = load_bundle(state["ticket_id"])
        claims = [Claim.model_validate(row) for row in (state.get("claims") or [])]
        verified = verify_claims(
            claims,
            email=bundle.email,
            policy=bundle.policy,
            decoy=bundle.decoy,
        )
        answers = load_answers(state["ticket_id"])
        return {
            "verified": [v.model_dump() for v in verified],
            "scores": task_scores(verified, answers),
        }

    def approve(state: DeskState) -> dict[str, Any]:
        if not interrupt_refunds or state.get("path") != "refund":
            return {"approved": True}
        decision = interrupt(
            {
                "awaiting": "refund_approval",
                "ticket_id": state.get("ticket_id"),
                "scores": state.get("scores") or {},
            }
        )
        return {"approved": decision in (True, "approve", "yes")}

    def draft(state: DeskState) -> dict[str, str]:
        if state.get("path") == "refund" and state.get("approved") is False:
            return {"draft": "Refund was not approved. No reply sent."}
        grounded = [
            row
            for row in (state.get("verified") or [])
            if row["status"] == "grounded"
        ]
        if not grounded:
            text = (
                "I cannot confirm this from the published policy. "
                "Please resend with a quote we can check."
            )
            return {"draft": text}

        lines = ["Based on the published policy:"]
        for row in grounded:
            claim = row["claim"]
            lines.append(f"- {claim['statement']} [{claim['span_id']}]")
        record = state.get("order_record")
        if record is not None and record.get("found") is False:
            lines.append(
                f"- Order {record.get('order_id')} is not on file; "
                "I cannot approve a refund against it."
            )
        return {"draft": "\n".join(lines)}

    builder = StateGraph(DeskState)
    builder.add_node("route", route)
    builder.add_node("extract", extract)
    builder.add_node("playbook", playbook)
    builder.add_node("gather", gather)
    builder.add_node("lookup_order", lookup_order)
    builder.add_node("verify", verify)
    builder.add_node("approve", approve)
    builder.add_node("draft", draft)

    builder.add_edge(START, "route")
    builder.add_edge("route", "extract")
    builder.add_edge("route", "playbook")
    builder.add_edge("extract", "gather")
    builder.add_edge("playbook", "gather")
    builder.add_conditional_edges(
        "gather", after_gather, ["lookup_order", "verify"]
    )
    builder.add_edge("lookup_order", "verify")
    builder.add_edge("verify", "approve")
    builder.add_edge("approve", "draft")
    builder.add_edge("draft", END)

    return builder.compile(checkpointer=checkpointer)


_graph: Any | None = None
_key: tuple[str, str, str, bool] | None = None


def get_app_graph(
    worker: DeskWorker | None = None,
    *,
    db_path: Path | None = None,
    interrupt_refunds: bool = True,
) -> Any:
    """Process-wide graph bound to sqlite so --thread-id survives a restart."""
    global _graph, _key
    worker = worker or live_worker()
    path = str(db_path) if db_path is not None else "default"
    key = (
        getattr(worker, "backend", "openai"),
        worker.model_name,
        path,
        interrupt_refunds,
    )
    if _graph is None or _key != key:
        saver = sqlite_saver(db_path)
        _graph = build_graph(
            worker, checkpointer=saver, interrupt_refunds=interrupt_refunds
        )
        _key = key
    return _graph


def ticket_input(ticket_id: str, *, condition: str = "clean") -> dict[str, Any]:
    bundle = load_bundle(ticket_id)
    policy = (
        bundle.noisy_policy_block if condition == "noisy" else bundle.policy_block
    )
    return {
        "ticket_id": ticket_id,
        "condition": condition,
        "email_text": bundle.email_block,
        "policy_prompt": policy,
        "claims": [],
        "lookup_ran": False,
    }


def invoke_ticket(
    ticket_id: str,
    *,
    condition: str = "clean",
    worker: DeskWorker | None = None,
    thread_id: str | None = None,
    graph: Any | None = None,
    interrupt_refunds: bool = True,
) -> dict[str, Any]:
    """Application entry. Only this function sets thread_id."""
    if graph is None:
        graph = get_app_graph(worker, interrupt_refunds=interrupt_refunds)
    tid = thread_id or ticket_id
    return graph.invoke(
        ticket_input(ticket_id, condition=condition),
        thread_config(tid),
    )


def resume_ticket(
    graph: Any,
    thread_id: str,
    *,
    approved: bool = True,
) -> dict[str, Any]:
    """Continue a paused refund on the same thread. Plane-only."""
    value = "approve" if approved else "reject"
    return graph.invoke(Command(resume=value), thread_config(thread_id))
