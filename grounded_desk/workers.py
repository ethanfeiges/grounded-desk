"""Live LangChain chat model for extract / playbook."""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI

from grounded_desk.models import Claim, ClaimBatch, PublicItem
from grounded_desk.prompts import SYSTEM, extract_user, playbook_user

DEFAULT_MODEL = "gpt-4o-mini"


def resolve_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def live_worker(model_name: str | None = None) -> "LangChainWorker":
    name = model_name or os.environ.get("GROUNDED_DESK_MODEL") or DEFAULT_MODEL
    return LangChainWorker(model_name=name)


class LangChainWorker:
    def __init__(
        self,
        model: Any | None = None,
        *,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        self.model = model
        self.model_name = model_name
        self._structured = (
            model.with_structured_output(ClaimBatch) if model is not None else None
        )

    def complete(
        self,
        task: str,
        ticket_id: str,
        **kwargs: Any,
    ) -> list[Claim]:
        del ticket_id
        items = [
            item if isinstance(item, PublicItem) else PublicItem.model_validate(item)
            for item in (kwargs.get("items") or [])
        ]
        email_block = str(kwargs.get("email_block") or "")
        policy_block = str(kwargs.get("policy_block") or "")
        path = str(kwargs.get("path") or "")
        if task == "extract":
            user = extract_user(
                email_block=email_block,
                policy_block=policy_block,
                path=path,
                items=items,
            )
        elif task == "playbook":
            user = playbook_user(
                email_block=email_block,
                policy_block=policy_block,
                path=path,
                items=items,
            )
        else:
            raise ValueError(f"no prompt for {task}")
        batch = self._client().invoke(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        if not isinstance(batch, ClaimBatch):
            batch = ClaimBatch.model_validate(batch)
        return batch.claims

    def _client(self) -> Any:
        if self._structured is None:
            key = resolve_api_key()
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY is required. This desk runs a live LangChain model only."
                )
            self.model = ChatOpenAI(model=self.model_name, api_key=key)
            self._structured = self.model.with_structured_output(ClaimBatch)
        return self._structured
