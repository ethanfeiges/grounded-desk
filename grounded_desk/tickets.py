from __future__ import annotations

import re
from dataclasses import dataclass

from grounded_desk.paths import EMAILS, ORDERS, POLICY_CANONICAL, POLICY_DECOY
from grounded_desk.stores import SpanStore, load_order, parse_span_file

ORDER_RE = re.compile(r"ORD-\d+")


@dataclass(frozen=True)
class TicketBundle:
    ticket_id: str
    email: SpanStore
    policy: SpanStore
    decoy: SpanStore
    email_block: str
    policy_block: str
    noisy_policy_block: str


def load_bundle(ticket_id: str) -> TicketBundle:
    email = parse_span_file(EMAILS / f"{ticket_id}.txt", source="email")
    policy = parse_span_file(POLICY_CANONICAL, source="policy")
    decoy = parse_span_file(POLICY_DECOY, source="decoy")
    email_block = email.format_block()
    policy_block = "signed_policy\n" + policy.format_block()
    noisy = (
        policy_block
        + "\n\ndraft_policy (do not cite)\n"
        + decoy.format_block()
    )
    return TicketBundle(
        ticket_id=ticket_id,
        email=email,
        policy=policy,
        decoy=decoy,
        email_block=email_block,
        policy_block=policy_block,
        noisy_policy_block=noisy,
    )


def find_order_id(text: str) -> str | None:
    match = ORDER_RE.search(text)
    return match.group(0) if match else None


def order_on_disk(order_id: str) -> dict | None:
    path = ORDERS / f"{order_id}.json"
    if not path.exists():
        return None
    return load_order(path)
