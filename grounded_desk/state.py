from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class DeskState(TypedDict, total=False):
    ticket_id: str
    condition: str
    email_text: str
    policy_prompt: str
    path: str
    claims: Annotated[list[dict[str, Any]], operator.add]
    verified: list[dict[str, Any]]
    scores: dict[str, bool]
    draft: str
    order_id: str | None
    order_record: dict[str, Any] | None
    lookup_ran: bool
    approved: bool | None
