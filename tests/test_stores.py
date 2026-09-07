from __future__ import annotations

from grounded_desk.stores import parse_span_file
from grounded_desk.tickets import find_order_id, load_bundle
from grounded_desk.paths import POLICY_CANONICAL


def test_policy_ids() -> None:
    store = parse_span_file(POLICY_CANONICAL, source="policy")
    assert store.contains("p-001")
    assert store.quote_matches("p-001", "thirty (30) days")
    assert not store.quote_matches("p-001", "fourteen (14) days")


def test_order_regex() -> None:
    bundle = load_bundle("missing_order")
    assert find_order_id(bundle.email_block) == "ORD-9999"
