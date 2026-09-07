from __future__ import annotations

from grounded_desk.models import Claim
from grounded_desk.tickets import load_bundle
from grounded_desk.verify import verify_claim


def test_canonical_quote_is_grounded() -> None:
    bundle = load_bundle("refund_day20")
    claim = Claim(
        statement="Window is 30 days.",
        span_id="p-001",
        quote="thirty (30) days",
        source="policy",
        rule_id="refund_window_30",
        verdict="pass",
    )
    verified = verify_claim(
        claim, email=bundle.email, policy=bundle.policy, decoy=bundle.decoy, task="playbook"
    )
    assert verified.status == "grounded"
    assert verified.decoy_match is None


def test_decoy_quote_is_rejected() -> None:
    bundle = load_bundle("refund_day20")
    claim = Claim(
        statement="Window is 14 days.",
        span_id="p-001",
        quote="fourteen (14) days",
        source="policy",
        rule_id="refund_window_30",
        verdict="fail",
    )
    verified = verify_claim(
        claim, email=bundle.email, policy=bundle.policy, decoy=bundle.decoy, task="playbook"
    )
    assert verified.status == "ungrounded"
    assert verified.reason == "text_mismatch"
    assert verified.decoy_match == "draft_policy"
