from __future__ import annotations

from fastapi.testclient import TestClient

from grounded_desk.graph import build_graph, ticket_input
from grounded_desk.checkpointing import sqlite_saver, thread_config
from grounded_desk.web import app
from grounded_desk.workers import make_worker


def test_health_and_tickets() -> None:
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["demo"] is True

    catalog = client.get("/api/tickets")
    ids = {row["ticket_id"] for row in catalog.json()["tickets"]}
    assert "refund_day20" in ids
    assert "missing_order" in ids

    detail = client.get("/api/tickets/refund_day20")
    assert detail.status_code == 200
    body = detail.json()
    assert "ORD-1001" in body["email"]
    assert "thirty (30) days" in body["policy"]
    assert "fourteen (14) days" in body["decoy"]


def test_demo_worker_writes_gold_aligned_claims() -> None:
    worker = make_worker("demo")
    extract = worker.complete("extract", "refund_day20")
    playbook = worker.complete("playbook", "refund_day20")
    assert {c.question_id for c in extract} == {"order_id", "age"}
    assert extract[0].quote == "ORD-1001" or extract[1].quote == "ORD-1001"
    assert {c.rule_id for c in playbook} == {"refund_window_30", "order_id_present"}


def test_demo_graph_completes_without_a_model(tmp_path) -> None:
    worker = make_worker("demo")
    graph = build_graph(
        worker,
        checkpointer=sqlite_saver(tmp_path / "tickets.sqlite"),
        interrupt_refunds=False,
    )
    result = graph.invoke(
        ticket_input("refund_day20"),
        thread_config("T-demo"),
    )
    assert result["path"] == "refund"
    assert result["approved"] is True
    assert result["draft"]
    assert result["scores"]["extract:order_id"] is True
    assert result["scores"]["playbook:refund_window_30"] is True
