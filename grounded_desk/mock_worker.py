"""Deterministic worker used by tests and the default CLI.

The mock is a stand-in for an isolated model call. It reads ticket_id + task
and returns Claim JSON. The `decoy` mode cites the 14-day draft on purpose
so the verifier can be shown to reject it.
"""

from __future__ import annotations

import json

from grounded_desk.models import Claim


class MockWorker:
    def __init__(self, mode: str = "canonical") -> None:
        if mode not in {"canonical", "decoy"}:
            raise ValueError(f"unknown worker mode {mode!r}")
        self.mode = mode

    def complete(self, task: str, ticket_id: str) -> str:
        claims = self._claims(task, ticket_id)
        return json.dumps({"claims": [c.model_dump() for c in claims]})

    def _claims(self, task: str, ticket_id: str) -> list[Claim]:
        if task == "extract":
            return _EXTRACT[ticket_id]
        if task == "playbook":
            if self.mode == "decoy" and ticket_id.startswith("refund"):
                return [_DECOY_WINDOW]
            return _PLAYBOOK[ticket_id]
        raise ValueError(f"mock has no script for task={task} ticket={ticket_id}")


_DECOY_WINDOW = Claim(
    statement="Refund window is 14 days; this purchase is outside it.",
    span_id="p-001",
    quote="fourteen (14) days",
    source="policy",
    rule_id="refund_window_30",
    verdict="fail",
)

_EXTRACT: dict[str, list[Claim]] = {
    "refund_day12": [
        Claim(
            statement="Customer order is ORD-1001.",
            span_id="e-001",
            quote="order ORD-1001",
            source="email",
            question_id="order_id",
        ),
        Claim(
            statement="Purchase was twelve days ago.",
            span_id="e-001",
            quote="twelve days ago",
            source="email",
            question_id="age",
        ),
    ],
    "refund_day20": [
        Claim(
            statement="Customer order is ORD-1001.",
            span_id="e-001",
            quote="order ORD-1001",
            source="email",
            question_id="order_id",
        ),
        Claim(
            statement="Purchase was twenty days ago.",
            span_id="e-001",
            quote="twenty days ago",
            source="email",
            question_id="age",
        ),
    ],
    "howto_password": [
        Claim(
            statement="Customer wants a password reset.",
            span_id="e-001",
            quote="reset my password",
            source="email",
            question_id="ask",
        ),
    ],
    "bug_crash": [
        Claim(
            statement="Crash was on iOS version 3.4.1.",
            span_id="e-001",
            quote="version 3.4.1",
            source="email",
            question_id="version",
        ),
    ],
    "missing_order": [
        Claim(
            statement="Customer cited ORD-9999.",
            span_id="e-001",
            quote="order ORD-9999",
            source="email",
            question_id="order_id",
        ),
    ],
}

_PLAYBOOK: dict[str, list[Claim]] = {
    "refund_day12": [
        Claim(
            statement="Twelve days is inside the 30-day window.",
            span_id="p-001",
            quote="thirty (30) days",
            source="policy",
            rule_id="refund_window_30",
            verdict="pass",
        ),
        Claim(
            statement="Order ID is present.",
            span_id="e-001",
            quote="ORD-1001",
            source="email",
            rule_id="order_id_present",
            verdict="pass",
        ),
    ],
    "refund_day20": [
        Claim(
            statement="Twenty days is inside the 30-day window.",
            span_id="p-001",
            quote="thirty (30) days",
            source="policy",
            rule_id="refund_window_30",
            verdict="pass",
        ),
        Claim(
            statement="Order ID is present.",
            span_id="e-001",
            quote="ORD-1001",
            source="email",
            rule_id="order_id_present",
            verdict="pass",
        ),
    ],
    "howto_password": [
        Claim(
            statement="Policy documents the reset path.",
            span_id="p-004",
            quote="Account, then Security, then Reset password",
            source="policy",
            rule_id="reset_path_documented",
            verdict="pass",
        ),
    ],
    "bug_crash": [
        Claim(
            statement="Version and time were included.",
            span_id="e-001",
            quote="version 3.4.1",
            source="email",
            rule_id="crash_fields",
            verdict="pass",
        ),
    ],
    "missing_order": [
        Claim(
            statement="Eight days is inside the 30-day window.",
            span_id="p-001",
            quote="thirty (30) days",
            source="policy",
            rule_id="refund_window_30",
            verdict="pass",
        ),
        Claim(
            statement="An order ID was provided.",
            span_id="e-001",
            quote="ORD-9999",
            source="email",
            rule_id="order_id_present",
            verdict="pass",
        ),
    ],
}
