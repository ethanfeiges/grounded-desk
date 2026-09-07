from __future__ import annotations

from grounded_desk.router import classify
from grounded_desk.tickets import load_bundle


def test_classifies_fixtures() -> None:
    expected = {
        "refund_day12": "refund",
        "refund_day20": "refund",
        "missing_order": "refund",
        "howto_password": "how_to",
        "bug_crash": "bug",
    }
    for ticket_id, path in expected.items():
        text = load_bundle(ticket_id).email_block
        assert classify(text) == path
