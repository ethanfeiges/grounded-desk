# How to read the graph

LangGraph is the runtime. The design is older than LangGraph.

**Process definition** — `build_graph()`: nodes and edges.  
**Process instance** — `thread_id` passed by `invoke_ticket`.  
**Work item** — one node execution on that thread (or one `Send` to `lookup_order`).

## Topologies stacked here

1. **Router.** `START → route`, then both specialists. The path is recorded on state so you can see what was chosen; extract/playbook currently share the same mock scripts keyed by ticket. A later change can branch prompts on `path` without moving the plane.
2. **Fan-out / fan-in.** `route → extract` and `route → playbook` in one super-step. `claims` uses `Annotated[list, operator.add]`. `gather` runs after both finish.
3. **Pipeline.** `verify → draft`.
4. **Supervisor slice.** `after_gather` may return `Send("lookup_order", …)` when the order file is missing. That creates a task on the **same** thread. It does not call `threads.create`.

Parallel writes without a reducer overwrite. That is why the reducer is on `claims` and not on `draft`.

## Isolation

Workers (`extract`, `playbook`) return JSON. They do not receive the answer YAML. They do not set `configurable.thread_id`. The test `test_workers_do_not_mint_thread_ids` reads their source.

Truth is `SpanStore` loaded from `fixtures/policies/canonical.txt` and the ticket email. The decoy file is passed into verify only so a bad quote can be labeled `draft_policy`. It is never accepted as grounded.

## Threads

`invoke_ticket(..., thread_id=...)` is the only supported way to start or resume a case. Two ticket ids on one compiled graph stay isolated if you give them two thread ids. Checkpoints are InMemorySaver in tests; swap the checkpointer in `new_thread_graph` if you want a file or Postgres later.

## Mapping to the vocabulary

| Word we used in study | Here |
|---|---|
| Control plane | `graph.py` edges, `classify`, `after_gather`, `invoke_ticket` |
| Worker | `extract`, `playbook` |
| Unit that is code | `verify`, `lookup_order`, `draft` |
| Run state | `DeskState` |
| Truth | span stores |
| Merge | `operator.add` on `claims`, then `verify` |
