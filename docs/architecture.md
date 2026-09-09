# How to read the graph

LangGraph is the runtime. The design is older than LangGraph.

**Process definition** — `build_graph()`: nodes and edges.  
**Process instance** — `thread_id` passed by `invoke_ticket`.  
**Work item** — one node execution on that thread (or one `Send` to `lookup_order`).

## Topologies stacked here

1. **Router.** `START → route`, then both specialists. The path is recorded on state so you can see what was chosen; extract/playbook currently share the same live prompts keyed by ticket. A later change can branch prompts on `path` without moving the plane.
2. **Fan-out / fan-in.** `route → extract` and `route → playbook` in one super-step. `claims` uses `Annotated[list, operator.add]`. `gather` runs after both finish.
3. **Pipeline.** `verify → approve → draft`. Refunds call `interrupt()` inside `approve`; how-to and bug skip it.
4. **Supervisor slice.** `after_gather` may return `Send("lookup_order", …)` when the order file is missing. That creates a task on the **same** thread. It does not call `threads.create`.

Parallel writes without a reducer overwrite. That is why the reducer is on `claims` and not on `draft`.

## Isolation

Workers (`extract`, `playbook`) return claims from a live model (OpenAI or Cursor). They do not receive the answer YAML. They do not set `configurable.thread_id`.

Truth is `SpanStore` loaded from `fixtures/policies/canonical.txt` and the ticket email. The decoy file is passed into verify only so a bad quote can be labeled `draft_policy`. It is never accepted as grounded.

## Threads

`invoke_ticket(..., thread_id=...)` starts a case. `resume_ticket` is the only way past a refund interrupt (`Command(resume=...)` on the same id). The CLI uses `SqliteSaver` at `.data/tickets.sqlite` via `get_app_graph` so a second process can `--status` / `--resume` the same thread. The policy files are still the source of truth; the sqlite file is run state only.

## Mapping to the vocabulary

| Word we used in study | Here |
|---|---|
| Control plane | `graph.py` edges, `classify`, `after_gather`, `invoke_ticket` |
| Worker | `extract`, `playbook` (live OpenAI or Cursor worker) |
| Unit that is code | `verify`, `lookup_order`, `draft` |
| Run state | `DeskState` |
| Truth | span stores |
| Merge | `operator.add` on `claims`, then `verify` |
| Thread / run memory | sqlite checkpointer |
