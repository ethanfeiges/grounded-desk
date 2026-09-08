from __future__ import annotations

from grounded_desk.answers import public_items
from grounded_desk.prompts import extract_user, playbook_user
from grounded_desk.tickets import load_bundle


def test_public_items_omit_gold() -> None:
    items = public_items("refund_day20", "playbook")
    dumped = " ".join(f"{i.id} {i.question}" for i in items)
    assert "refund_window_30" in dumped
    assert "pass" not in dumped.lower()
    assert "thirty" not in dumped
    assert "p-001" not in dumped


def test_prompts_omit_gold() -> None:
    bundle = load_bundle("refund_day20")
    items = public_items("refund_day20", "extract")
    user = extract_user(
        email_block=bundle.email_block,
        policy_block=bundle.policy_block,
        path="refund",
        items=items,
    )
    assert "acceptable_span_ids" not in user
    assert "required_substrings" not in user
    play = playbook_user(
        email_block=bundle.email_block,
        policy_block=bundle.policy_block,
        path="refund",
        items=public_items("refund_day20", "playbook"),
    )
    assert "expected" not in play
    assert "canonical_span" not in play
