from __future__ import annotations

import inspect

import pytest

from grounded_desk import graph as graph_module
from grounded_desk.workers import live_worker


def test_live_worker_constructs_without_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    worker = live_worker("gpt-4o-mini")
    assert worker.model_name == "gpt-4o-mini"
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        worker.complete("extract", "refund_day20", items=[])


def test_workers_do_not_mint_thread_ids() -> None:
    source = inspect.getsource(graph_module)
    extract_fn = _function_body(source, "def extract")
    playbook_fn = _function_body(source, "def playbook")
    assert "thread_id" not in extract_fn
    assert "thread_id" not in playbook_fn
    assert "invoke(" not in extract_fn
    assert "invoke(" not in playbook_fn


def _function_body(source: str, header: str) -> str:
    start = source.index(header)
    rest = source[start:]
    lines = rest.splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line.startswith("    def ") or line.startswith("    builder"):
            break
        body.append(line)
    return "\n".join(body)
