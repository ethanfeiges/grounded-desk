"""CLI. Thread ids are chosen here, not inside worker nodes."""

from __future__ import annotations

import argparse
import json
import sys

from grounded_desk.graph import invoke_ticket
from grounded_desk.mock_worker import MockWorker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one support ticket through the desk.")
    parser.add_argument("ticket_id", help="fixture id, e.g. refund_day20")
    parser.add_argument(
        "--condition",
        choices=("clean", "noisy"),
        default="clean",
        help="noisy puts the 14-day draft in the prompt",
    )
    parser.add_argument(
        "--worker",
        choices=("canonical", "decoy"),
        default="canonical",
        help="decoy cites the draft policy (for showing the verifier)",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="defaults to ticket_id; pass this yourself, not from a worker",
    )
    args = parser.parse_args(argv)

    result = invoke_ticket(
        args.ticket_id,
        condition=args.condition,
        worker=MockWorker(args.worker),
        thread_id=args.thread_id,
    )
    print(result["draft"])
    print()
    print(
        json.dumps(
            {
                "path": result.get("path"),
                "scores": result.get("scores"),
                "lookup_ran": result.get("lookup_ran"),
                "order_record": result.get("order_record"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
