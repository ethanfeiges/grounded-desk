"""Compiled desk graph.

Control plane is this file: edges, the keyword router, and the gather
conditional. extract and playbook are workers. verify is a code unit.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from grounded_desk.answers import load_answers
from grounded_desk.mock_worker import MockWorker
from grounded_desk.router import classify
from grounded_desk.score import parse_claims, task_scores
from grounded_desk.state import DeskState
from grounded_desk.tickets import find_order_id, load_bundle, order_on_disk
from grounded_desk.verify import verify_claims


def build_graph(
    worker: MockWorker | None = None,
    *,
    checkpointer: Any | None = None,
) -> Any:
    worker = worker or MockWorker("canonical")

    def route(state: DeskState) -> dict[str, str]:
        return {"path": classify(state["email_text"])}

    def extract(state: DeskState) -> dict[str, Any]:
        raw = worker.complete("extract", state["ticket_id"])
        claims = [c.model_dump() for c in parse_claims(raw)]
        return {"claims": claims}

    def playbook(state: DeskState) -> dict[str, Any]:
        raw = worker.complete("playbook", state["ticket_id"])
        claims = [c.model_dump() for c in parse_claims(raw)]
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
        from grounded_desk.models import Claim

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

    def draft(state: DeskState) -> dict[str, str]:
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
    builder.add_edge("verify", "draft")
    builder.add_edge("draft", END)

    return builder.compile(checkpointer=checkpointer)


def new_thread_graph(worker: MockWorker | None = None) -> tuple[Any, InMemorySaver]:
    saver = InMemorySaver()
    return build_graph(worker, checkpointer=saver), saver


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
    worker: MockWorker | None = None,
    thread_id: str | None = None,
    graph: Any | None = None,
) -> dict[str, Any]:
    """Application entry. Only this function sets thread_id."""
    if graph is None:
        graph, _ = new_thread_graph(worker)
    tid = thread_id or ticket_id
    return graph.invoke(
        ticket_input(ticket_id, condition=condition),
        {"configurable": {"thread_id": tid}},
    )


def worker_source() -> str:
    """Used by tests to assert workers do not mint threads."""
    import inspect

    from grounded_desk import graph as module

    return inspect.getsource(module)
