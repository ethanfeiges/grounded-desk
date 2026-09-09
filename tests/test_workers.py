from __future__ import annotations

import inspect

import pytest

from grounded_desk import graph as graph_module
from grounded_desk.workers import make_worker, parse_claim_batch


def test_demo_backend_is_available() -> None:
    worker = make_worker("demo")
    assert worker.backend == "demo"
    assert worker.model_name == "fixture"


def test_live_worker_constructs_without_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    worker = make_worker("openai", "gpt-4o-mini")
    assert worker.model_name == "gpt-4o-mini"
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        worker.complete("extract", "refund_day20", items=[])


def test_cursor_worker_constructs_without_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    worker = make_worker("cursor", "composer-2.5")
    assert worker.backend == "cursor"
    assert worker.model_name == "composer-2.5"
    with pytest.raises(RuntimeError, match="CURSOR_API_KEY"):
        worker.complete("extract", "refund_day20", items=[])


def test_parse_claim_batch_accepts_fenced_json() -> None:
    claims = parse_claim_batch(
        '```json\n{"claims": [{"statement": "order", "span_id": "e-001", '
        '"quote": "ORD-1001", "source": "email", "question_id": "order_id"}]}\n```'
    )
    assert claims[0].quote == "ORD-1001"


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
