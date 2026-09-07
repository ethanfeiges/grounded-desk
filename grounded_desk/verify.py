"""Mechanical check against canonical stores. No model."""

from __future__ import annotations

from grounded_desk.models import Claim, VerifiedClaim
from grounded_desk.stores import SpanStore


def verify_claim(
    claim: Claim,
    *,
    email: SpanStore,
    policy: SpanStore,
    decoy: SpanStore | None = None,
    task: str,
) -> VerifiedClaim:
    store = email if claim.span_id.startswith("e-") else policy
    decoy_match: str | None = None

    if not store.contains(claim.span_id):
        status = "ungrounded"
        reason = "missing_span"
    elif not store.quote_matches(claim.span_id, claim.quote):
        status = "ungrounded"
        reason = "text_mismatch"
    else:
        status = "grounded"
        reason = None

    if status == "ungrounded" and decoy is not None:
        if decoy.quote_matches(claim.span_id, claim.quote) or decoy.find_quote(
            claim.quote
        ):
            decoy_match = "draft_policy"

    return VerifiedClaim(
        claim=claim,
        status=status,
        reason=reason,
        decoy_match=decoy_match,
        task=task,
    )


def verify_claims(
    claims: list[Claim],
    *,
    email: SpanStore,
    policy: SpanStore,
    decoy: SpanStore | None = None,
) -> list[VerifiedClaim]:
    out: list[VerifiedClaim] = []
    for claim in claims:
        task = "playbook" if claim.rule_id else "extract"
        out.append(
            verify_claim(
                claim, email=email, policy=policy, decoy=decoy, task=task
            )
        )
    return out
