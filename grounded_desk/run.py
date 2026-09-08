"""CLI. Thread ids are chosen here, not inside worker nodes."""

from __future__ import annotations

import argparse
import json
import sys

from grounded_desk.checkpointing import interrupt_payloads, pending_nodes, thread_config
from grounded_desk.graph import get_app_graph, resume_ticket, ticket_input
from grounded_desk.workers import live_worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one support ticket through the desk.")
    parser.add_argument(
        "ticket_id",
        nargs="?",
        help="fixture id, e.g. refund_day20 (omit with --resume / --status)",
    )
    parser.add_argument(
        "--condition",
        choices=("clean", "noisy"),
        default="clean",
        help="noisy puts the 14-day draft in the prompt",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="defaults to ticket_id; pass this yourself, not from a worker",
    )
    parser.add_argument(
        "--resume",
        metavar="THREAD",
        default=None,
        help="continue a paused refund on this thread",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="with --resume, approve the refund and write the draft",
    )
    parser.add_argument(
        "--reject",
        action="store_true",
        help="with --resume, refuse the refund",
    )
    parser.add_argument(
        "--status",
        metavar="THREAD",
        default=None,
        help="print pending nodes for a thread (get_state().next)",
    )
    parser.add_argument(
        "--skip-approval",
        action="store_true",
        help="do not pause refunds",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LangChain chat model id (default gpt-4o-mini)",
    )
    args = parser.parse_args(argv)

    graph = get_app_graph(
        live_worker(args.model),
        interrupt_refunds=not args.skip_approval,
    )

    if args.status:
        nodes = pending_nodes(graph, args.status)
        print(json.dumps({"thread_id": args.status, "next": nodes}, indent=2))
        return 0

    if args.resume:
        if args.approve and args.reject:
            parser.error("use only one of --approve / --reject")
        result = resume_ticket(
            graph, args.resume, approved=not args.reject
        )
        return _print_result(graph, args.resume, result)

    if not args.ticket_id:
        parser.error("ticket_id is required unless you pass --resume or --status")

    thread_id = args.thread_id or args.ticket_id
    result = graph.invoke(
        ticket_input(args.ticket_id, condition=args.condition),
        thread_config(thread_id),
    )
    return _print_result(graph, thread_id, result)


def _print_result(graph, thread_id: str, result: dict) -> int:
    paused = interrupt_payloads(result)
    nxt = pending_nodes(graph, thread_id)
    if paused:
        print("Paused. Refunds wait for approval on this thread.")
        print(json.dumps({"thread_id": thread_id, "next": nxt, "interrupt": paused}, indent=2))
        print(f"Resume: python -m grounded_desk.run --resume {thread_id} --approve")
        return 0
    print(result.get("draft") or "")
    print()
    print(
        json.dumps(
            {
                "path": result.get("path"),
                "scores": result.get("scores"),
                "lookup_ran": result.get("lookup_ran"),
                "order_record": result.get("order_record"),
                "approved": result.get("approved"),
                "next": nxt,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
