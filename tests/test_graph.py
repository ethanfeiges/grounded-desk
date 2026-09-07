from __future__ import annotations

from grounded_desk.graph import invoke_ticket, new_thread_graph, worker_source
from grounded_desk.mock_worker import MockWorker


def test_refund_clean_passes(canonical: MockWorker) -> None:
    result = invoke_ticket("refund_day20", worker=canonical)
    assert result["path"] == "refund"
    assert result["scores"]["playbook:refund_window_30"] is True
    assert result["scores"]["extract:order_id"] is True
    assert "[p-001]" in result["draft"]
    assert result.get("lookup_ran") in (False, None)


def test_parallel_claims_are_kept(canonical: MockWorker) -> None:
    result = invoke_ticket("refund_day20", worker=canonical)
    question_ids = {
        c.get("question_id") for c in result["claims"] if c.get("question_id")
    }
    rule_ids = {c.get("rule_id") for c in result["claims"] if c.get("rule_id")}
    assert "order_id" in question_ids
    assert "refund_window_30" in rule_ids


def test_decoy_worker_fails_window_rule(decoy: MockWorker) -> None:
    result = invoke_ticket("refund_day20", condition="noisy", worker=decoy)
    window = [
        row
        for row in result["verified"]
        if row["claim"].get("rule_id") == "refund_window_30"
    ]
    assert window
    assert window[0]["status"] == "ungrounded"
    assert window[0]["decoy_match"] == "draft_policy"
    assert result["scores"]["playbook:refund_window_30"] is False


def test_missing_order_runs_lookup(canonical: MockWorker) -> None:
    result = invoke_ticket("missing_order", worker=canonical)
    assert result["lookup_ran"] is True
    assert result["order_record"]["found"] is False
    assert "not on file" in result["draft"]


def test_threads_are_isolated(canonical: MockWorker) -> None:
    graph, _ = new_thread_graph(canonical)
    invoke_ticket("refund_day20", worker=canonical, thread_id="t-a", graph=graph)
    invoke_ticket("howto_password", worker=canonical, thread_id="t-b", graph=graph)
    a = graph.get_state({"configurable": {"thread_id": "t-a"}}).values
    b = graph.get_state({"configurable": {"thread_id": "t-b"}}).values
    assert a["ticket_id"] == "refund_day20"
    assert b["ticket_id"] == "howto_password"
    assert a["path"] == "refund"
    assert b["path"] == "how_to"


def test_same_thread_resumes(canonical: MockWorker) -> None:
    graph, _ = new_thread_graph(canonical)
    invoke_ticket("refund_day20", worker=canonical, thread_id="t-1", graph=graph)
    history = list(graph.get_state_history({"configurable": {"thread_id": "t-1"}}))
    assert history
    snap = graph.get_state({"configurable": {"thread_id": "t-1"}})
    assert snap.values["draft"]


def test_workers_do_not_mint_thread_ids() -> None:
    source = worker_source()
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
