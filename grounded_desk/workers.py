"""Live model workers for extract / playbook."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from typing import Any, Literal, Mapping, Protocol

from grounded_desk.answers import load_answers
from grounded_desk.models import Claim, ClaimBatch, PublicItem
from grounded_desk.prompts import JSON_ONLY, SYSTEM, extract_user, playbook_user

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_CURSOR_MODEL = "composer-2.5"
Backend = Literal["openai", "cursor"]


class DeskWorker(Protocol):
    backend: str
    model_name: str

    def complete(self, task: str, ticket_id: str, **kwargs: Any) -> list[Claim]: ...


def resolve_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def resolve_cursor_api_key() -> str:
    return os.environ.get("CURSOR_API_KEY", "").strip()


def live_worker(model_name: str | None = None) -> LangChainWorker:
    name = model_name or os.environ.get("GROUNDED_DESK_MODEL") or DEFAULT_OPENAI_MODEL
    return LangChainWorker(model_name=name)


def make_worker(
    backend: str | None = None,
    model_name: str | None = None,
) -> DeskWorker:
    kind = (backend or os.environ.get("GROUNDED_DESK_BACKEND") or "openai").strip().lower()
    if kind == "demo":
        return DemoWorker(model_name=model_name or "fixture")
    if kind == "cursor":
        name = model_name or os.environ.get("GROUNDED_DESK_MODEL") or DEFAULT_CURSOR_MODEL
        return CursorWorker(model_name=name)
    if kind == "openai":
        return live_worker(model_name)
    raise ValueError(f"unknown backend {backend!r}; use openai, cursor, or demo")


def render_task_prompt(task: str, **kwargs: Any) -> str:
    items = [
        item if isinstance(item, PublicItem) else PublicItem.model_validate(item)
        for item in (kwargs.get("items") or [])
    ]
    email_block = str(kwargs.get("email_block") or "")
    policy_block = str(kwargs.get("policy_block") or "")
    path = str(kwargs.get("path") or "")
    if task == "extract":
        return extract_user(
            email_block=email_block,
            policy_block=policy_block,
            path=path,
            items=items,
        )
    if task == "playbook":
        return playbook_user(
            email_block=email_block,
            policy_block=policy_block,
            path=path,
            items=items,
        )
    raise ValueError(f"no prompt for {task}")


def parse_claim_batch(text: str) -> list[Claim]:
    payload = _extract_json(text)
    batch = ClaimBatch.model_validate(payload)
    return batch.claims


class DemoWorker:
    """Replay gold-aligned claims so the graph can run without a model key."""

    backend = "demo"

    def __init__(self, *, model_name: str = "fixture") -> None:
        self.model_name = model_name

    def complete(self, task: str, ticket_id: str, **kwargs: Any) -> list[Claim]:
        del kwargs
        answers = load_answers(ticket_id)
        if task == "extract":
            return [
                Claim(
                    statement=question.question,
                    span_id=question.acceptable_span_ids[0],
                    quote=question.required_substrings[0],
                    source=_source_for(question.acceptable_span_ids[0]),
                    question_id=question.id,
                )
                for question in answers.extract_questions
                if question.acceptable_span_ids and question.required_substrings
            ]
        if task == "playbook":
            return [
                Claim(
                    statement=rule.question,
                    span_id=rule.canonical_span_ids[0],
                    quote=rule.required_substrings[0],
                    source=_source_for(rule.canonical_span_ids[0]),
                    rule_id=rule.id,
                    verdict=rule.expected,
                )
                for rule in answers.rules
                if rule.canonical_span_ids and rule.required_substrings
            ]
        raise ValueError(f"no demo claims for {task}")


def _source_for(span_id: str) -> str:
    return "email" if span_id.startswith("e-") else "policy"


class LangChainWorker:
    backend = "openai"

    def __init__(
        self,
        model: Any | None = None,
        *,
        model_name: str = DEFAULT_OPENAI_MODEL,
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
        user = render_task_prompt(task, **kwargs)
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
            from langchain_openai import ChatOpenAI

            key = resolve_api_key()
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY is required for --backend openai."
                )
            self.model = ChatOpenAI(model=self.model_name, api_key=key)
            self._structured = self.model.with_structured_output(ClaimBatch)
        return self._structured


_CURSOR_LOCK = threading.Lock()
_WINDOWS_BRIDGE_PATCHED = False


class CursorWorker:
    backend = "cursor"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_CURSOR_MODEL,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name
        self._api_key = api_key

    def complete(
        self,
        task: str,
        ticket_id: str,
        **kwargs: Any,
    ) -> list[Claim]:
        del ticket_id
        key = (self._api_key or resolve_cursor_api_key()).strip()
        if not key:
            raise RuntimeError(
                "CURSOR_API_KEY is required for --backend cursor. "
                "Mint one at https://cursor.com/dashboard/integrations"
            )
        user = render_task_prompt(task, **kwargs)
        message = f"{SYSTEM}\n\n{user}\n\n{JSON_ONLY}"
        # extract ∥ playbook share one Windows-safe bridge; serialize the two calls.
        with _CURSOR_LOCK:
            text = self._prompt(key, message)
        return parse_claim_batch(text)

    def _prompt(self, api_key: str, message: str) -> str:
        from cursor_sdk import (
            Agent,
            AgentOptions,
            CursorAgentError,
            LocalAgentOptions,
        )

        _patch_windows_bridge_reader()
        cwd = tempfile.mkdtemp(prefix="grounded-desk-")
        try:
            result = Agent.prompt(
                message,
                AgentOptions(
                    api_key=api_key,
                    model=self.model_name,
                    tools=[],
                    local=LocalAgentOptions(cwd=cwd),
                ),
            )
        except CursorAgentError as err:
            raise RuntimeError(
                f"Cursor startup failed: {err.message} "
                f"(retryable={getattr(err, 'is_retryable', False)})"
            ) from err

        status = getattr(result, "status", None)
        if status == "error":
            raise RuntimeError(
                f"Cursor run failed: {getattr(result, 'id', 'unknown')}"
            )
        return _result_text(result)


def _patch_windows_bridge_reader() -> None:
    """cursor-sdk uses select() on a pipe; that raises WinError 10038."""
    global _WINDOWS_BRIDGE_PATCHED
    if _WINDOWS_BRIDGE_PATCHED or os.name != "nt":
        return
    from cursor_sdk import _bridge

    _bridge._read_discovery = _read_discovery_threaded  # type: ignore[method-assign]
    _WINDOWS_BRIDGE_PATCHED = True


def _read_discovery_threaded(
    process: Any, timeout: float
) -> Mapping[str, Any]:
    from cursor_sdk._bridge import parse_discovery_line
    from cursor_sdk.errors import CursorSDKError

    if process.stderr is None:
        raise CursorSDKError("Bridge process stderr is unavailable")

    found: dict[str, Mapping[str, Any]] = {}
    lines: list[str] = []
    errors: list[BaseException] = []

    def reader() -> None:
        try:
            for line in process.stderr:
                lines.append(line)
                discovery = parse_discovery_line(line)
                if discovery is not None:
                    found["discovery"] = discovery
                    return
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if found:
            return found["discovery"]
        if errors:
            raise errors[0]
        if process.poll() is not None and not thread.is_alive():
            if found:
                return found["discovery"]
            raise CursorSDKError(
                "Bridge exited before discovery with status "
                f"{process.returncode}: {''.join(lines)}"
            )
        thread.join(timeout=0.1)
    raise CursorSDKError("Timed out waiting for bridge discovery")


def _result_text(result: Any) -> str:
    raw = getattr(result, "result", result)
    if raw is None:
        raise RuntimeError("Cursor run returned no text")
    if isinstance(raw, str):
        return raw
    return str(raw)


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"Cursor reply was not JSON: {text[:400]}")
        return json.loads(stripped[start : end + 1])
