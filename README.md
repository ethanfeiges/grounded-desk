# Grounded Desk

A support desk that may answer only from a published policy and the ticket email. The model can be shown a decoy policy. The checker cannot.

This repo is a LangGraph workflow: units of work, a control plane that owns scheduling, and a store nobody on the model side can write. extract and playbook call a live LangChain chat model.

```
START → route → extract ∥ playbook → gather → lookup? → verify → approve → draft → END
```

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Set `OPENAI_API_KEY`. Optional: `GROUNDED_DESK_MODEL` (default `gpt-4o-mini`).

## Run

Refunds pause after verify until you approve on the same thread. How-to and bug tickets do not.

```powershell
python -m grounded_desk.run refund_day20 --thread-id T-2041
python -m grounded_desk.run --status T-2041
python -m grounded_desk.run --resume T-2041 --approve
```

Skip the pause for a one-shot:

```powershell
python -m grounded_desk.run refund_day20 --skip-approval
python -m grounded_desk.run refund_day20 --condition noisy --skip-approval
python -m grounded_desk.run missing_order --skip-approval
```

`--condition noisy` puts the 14-day draft in the prompt so you can watch `refund_window_30` fail if the model cites it.

Fixtures: `fixtures/emails/`, gold in `fixtures/answers/{ticket_id}.yaml`, published policy in `fixtures/policies/canonical.txt`, trap in `decoy_14_day.txt`. Known order file: `fixtures/orders/ORD-1001.json`.

## Layout

```
grounded_desk/     StateGraph, stores, verifier, live LangChain worker
fixtures/          emails, policies, answer keys, one order
docs/              unit contracts
tests/             mechanical checks on stores, router, verifier, prompts
```

---

## LangGraph, as this graph uses it

LangGraph models a program as a **graph**: shared **state**, **nodes** that write updates, **edges** that pick the next node. Official line: nodes do the work, edges tell what to do next. You assemble a `StateGraph`, then `compile()` it. Compile is where the checkpointer is attached and where orphaned nodes are rejected. You cannot `invoke` an uncompiled builder.

What follows is every primitive this desk actually depends on.

### State

`DeskState` in `grounded_desk/state.py` is the schema every node reads. It is a `TypedDict`. Nodes return **partial updates** (`{"path": "refund"}`), not a mutated object. That snapshot is run state: claims, scores, draft, which ticket. It is not the published policy. Policy text lives in `SpanStore` files; workers cannot write those channels.

### Reducers

Each key has a reducer: how two updates to the same field combine. The default is **overwrite**. Parallel nodes that both write `claims` would clobber each other. So `claims` is `Annotated[list, operator.add]` — append, do not replace. `draft` and `verified` stay overwrite: there should be one of each per run. If you drop the reducer on `claims`, last-write-wins and one worker’s output disappears. That is the fan-in bug LangGraph will not catch for you.

### Nodes

A node is a function `(state) -> update`. In this repo:


| Node                  | Kind                                             |
| --------------------- | ------------------------------------------------ |
| `route`               | Classifier. Writes `path`. Not a support answer. |
| `extract`, `playbook` | Workers. Write `claims`.                         |
| `gather`              | Fan-in wait. Writes `order_id`.                  |
| `lookup_order`        | Code unit, spawned only when needed.             |
| `verify`              | Code unit. Writes `verified` and `scores`.       |
| `approve`             | Control. May `interrupt()`. Writes `approved`.   |
| `draft`               | Code unit. Writes `draft`.                       |


Every unit of work is a node. Not every node is a unit of work: `gather` exists so both workers finish before the next edge runs.

### Edges, START, END

`add_edge("verify", "approve")` is a fixed hop. `START` is the entry; `END` is the stop. Conditional edges (`after_gather`) read state and return a node name or a `Send`. Edges are the control plane. A worker that returned `Command(goto=...)` would be sitting in that plane; extract and playbook are not allowed to.

### Super-steps

The runtime is Pregel-style. A **super-step** is one tick: every node that is ready runs, then a checkpoint is written. Nodes with no data dependency of each other run in the **same** super-step (extract ∥ playbook). Nodes that need the previous result run in a **later** super-step (verify after gather). A parallel super-step is transactional: if one sibling raises, that tick’s updates are not committed. Resume after a crash is from a super-step boundary, not from the middle of a node.

### Fan-out and fan-in

Two edges leave `route` for `extract` and `playbook`. That is static fan-out. Both finish, then `gather` runs. Fan-in is not a special type — it is “a node whose incoming edges are all satisfied.” The reducer is what makes the join lossless.

### Router

`route` is exclusive choice: it stamps `path` (`refund` / `how_to` / `bug`). Today both workers still run so the fan-out lesson stays visible; `path` is on state so a later change can send only one specialist without moving truth or verify. A misroute is a control-plane error, not a “dumb extract.”

### Send

`Send("lookup_order", {order_id, ...})` creates a task at **runtime** when the units were not all known at compile time (the order file is missing). The payload is the state that `lookup_order` sees. Outputs reduce back into the **same** thread. `Send` is not a new thread and not `threads.create`.

### Threads

A **thread** is one case walking the compiled graph, keyed by `thread_id` in `{"configurable": {"thread_id": ...}}`. It is not an OS thread and not a worker. Two tickets are two thread ids on one compiled graph. The CLI is the only place that mints that id. Reusing it loads the last checkpoint; a new id starts empty.

### Checkpointers

`compile(checkpointer=...)` snapshots `DeskState` after each super-step, indexed by thread. The CLI uses `SqliteSaver` at `.data/tickets.sqlite` so `--status` and `--resume` work after you close the shell.

That is short-term, thread-scoped **run** memory: where the ticket is, what claims exist, whether we are waiting on approve. It is not the policy store. A LangGraph Store (cross-thread facts) is a different object and is not used here.

What the checkpointer is for, on this desk:

- Isolation: `T-2041` vs `T-2042` do not share claims.
- Resume: same id after interrupt or process restart.
- History: `get_state_history` / `get_state().next` (`--status`).
- Fault tolerance: pending writes from a sibling that finished in a failed super-step.

### Interrupts and Command

Refunds call `interrupt({...})` inside `approve`. The graph stops, the payload comes back on `__interrupt__`, and `next` is `approve`. Resume is `Command(resume="approve"|"reject")` on the **same** `thread_id`. The node restarts from the top of `approve`; `interrupt()` then returns the resume value instead of pausing. How-to and bug skip `interrupt` and set `approved=True`. `--skip-approval` compiles the graph without that pause.

`Command` as **input** to `invoke` is only for `resume` here. Do not pass `Command(goto=...)` from extract.

### Compile, invoke, get_state

```python
graph = builder.compile(checkpointer=saver)
graph.invoke(ticket_input(...), {"configurable": {"thread_id": tid}})
graph.get_state(config).next    # queued node names
graph.get_state_history(config) # checkpoints for that thread
```

`invoke` with a full `ticket_input` starts (or restarts) a walk. `invoke` with `Command(resume=...)` continues a paused one. Mixing those two is how you accidentally re-run extract on an already-verified ticket.

---

Workers do not start threads. There is no lead agent. For the legal-document experiment with the same split (canonical store, decoys, parallel tasks), see lexorchestra.
