"""Worker prompts. Questions only — no gold spans or expected verdicts."""

from __future__ import annotations

from grounded_desk.models import ClaimBatch, PublicItem

SYSTEM = (
    "You are a support analyst. Cite only from signed_policy and the email. "
    "If a draft_policy block is present, do not quote it. "
    "Reply with claims that use exact substrings from the allowed blocks."
)

JSON_ONLY = (
    "Reply with JSON only. No markdown. No tools. No file access. "
    "Shape: {\"claims\": [{\"statement\": str, \"span_id\": str, \"quote\": str, "
    "\"source\": \"email\"|\"policy\"|null, \"question_id\": str|null, "
    "\"rule_id\": str|null, \"verdict\": \"pass\"|\"fail\"|null}]}. "
    "quote must be an exact substring of signed_policy or the email. "
    f"Schema: {ClaimBatch.model_json_schema()}"
)


def extract_user(
    *,
    email_block: str,
    policy_block: str,
    path: str,
    items: list[PublicItem],
) -> str:
    questions = "\n".join(f"- question_id={i.id}: {i.question}" for i in items)
    return (
        f"Ticket path: {path}\n\n"
        f"{policy_block}\n\n"
        f"email\n{email_block}\n\n"
        f"Answer each extract question.\n{questions}\n"
    )


def playbook_user(
    *,
    email_block: str,
    policy_block: str,
    path: str,
    items: list[PublicItem],
) -> str:
    rules = "\n".join(f"- rule_id={i.id}: {i.question}" for i in items)
    return (
        f"Ticket path: {path}\n\n"
        f"{policy_block}\n\n"
        f"email\n{email_block}\n\n"
        f"For each rule, verdict pass or fail with a quote.\n{rules}\n"
    )
