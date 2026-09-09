# Grounded Desk

A support desk that may answer only from a published policy and the ticket email. The model can be shown a decoy policy. The checker cannot.

This repo is a LangGraph workflow: units of work, a control plane that owns scheduling, and a store nobody on the model side can write. extract and playbook call a live model (`--backend openai` or `--backend cursor`), or replay fixture claims (`--backend demo`).

```
START → route → extract ∥ playbook → gather → lookup? → verify → approve → draft → END
```

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

For Cursor (no OpenAI key):

```powershell
pip install -e ".[cursor]"
$env:CURSOR_API_KEY = "crsr_..."   # https://cursor.com/dashboard/integrations
```

Optional: `GROUNDED_DESK_MODEL` (Cursor default `composer-2.5`). `--backend cursor` is required unless you set `GROUNDED_DESK_BACKEND=cursor`.

For OpenAI instead: set `OPENAI_API_KEY` and omit `--backend` (or pass `--backend openai`).

## Run

Refunds pause after verify until you approve on the same thread. How-to and bug tickets do not.

```powershell
python -m grounded_desk.run refund_day20 --backend cursor --thread-id T-2041
python -m grounded_desk.run --status T-2041
python -m grounded_desk.run --resume T-2041 --approve
```

Skip the pause for a one-shot:

```powershell
python -m grounded_desk.run refund_day20 --backend cursor --skip-approval
python -m grounded_desk.run refund_day20 --backend cursor --condition noisy --skip-approval
python -m grounded_desk.run missing_order --backend cursor --skip-approval
```

`--condition noisy` puts the 14-day draft in the prompt so you can watch `refund_window_30` fail if the model cites it.

`--backend demo` skips the model and writes gold-aligned claims so you can watch the rest of the graph (gather, lookup, verify, approve, draft) without an API key. The live workers never see that gold file; demo is a replay for the UI and for local walkthroughs.

## Live UI

A localhost board that streams each node as it writes into `DeskState`. Pick a ticket, run it, watch claims appear, then approve a paused refund on the same thread.

```powershell
pip install -e .
python -m grounded_desk.web
```

Then open http://127.0.0.1:8000. Default backend is `demo` (no key). Switch to `openai` or `cursor` in the form if those keys are set. `--host` / `--port` / `--reload` are optional.

What you are looking at:

- The graph row is the walk above. A node lights when it starts, then stamps done when its update lands.
- The three paper panels are the email, the published policy, and the decoy. Verify only accepts quotes from the first two.
- **Claims** are the cited facts the workers wrote. After `verify`, each one is stamped `grounded` or `ungrounded`.
- **Scores** compare those grounded hits to `fixtures/answers/{ticket}.yaml`.
- **Draft** is assembled only from grounded claims (or a refusal).
- Refunds pause on `approve` until you click Approve or Reject. That is the same `interrupt()` the CLI resumes with `--resume`.

Fixtures: `fixtures/emails/`, gold in `fixtures/answers/{ticket_id}.yaml`, published policy in `fixtures/policies/canonical.txt`, trap in `decoy_14_day.txt`. Known order file: `fixtures/orders/ORD-1001.json`.

## Layout

```
grounded_desk/     StateGraph, stores, verifier, workers, localhost UI
fixtures/          emails, policies, answer keys, one order
docs/              unit contracts
tests/             mechanical checks on stores, router, verifier, prompts
```

---

## How a ticket walks the graph

LangGraph is a state machine. One ticket is one walk. Shared memory for that walk is **`DeskState`**. The model never writes the customer reply. It writes **claims**. Later nodes check those claims against files the model cannot edit, then `draft` turns the ones that passed into a reply.

Take `refund_day20`. The email is two numbered lines:

```
[e-001] Hello, I purchased a desk lamp ... twenty days ago (order ORD-1001).
[e-002] It works, but I want to return it. Am I still inside the refund window?
```

The published policy is six numbered lines in `fixtures/policies/canonical.txt`. The important one is:

```
[p-001] Customers may request a refund within thirty (30) days of the purchase date.
```

Those `[e-001]` / `[p-001]` labels are **span ids**. A span is one citable sentence. The model must point at a span and copy a substring from it. That pair — “this sentence, from this line” — is a claim.

### DeskState is the case file

`DeskState` (`grounded_desk/state.py`) is a `TypedDict`: a bag of named fields that travel with the ticket. It is **this run’s working memory**. It is not the published policy. Policy text lives in `SpanStore` files under `fixtures/policies/`. Workers can read a *copy* of that text in `policy_prompt`. They cannot write the store.

LangGraph does not hand a node a mutable object to edit in place. A node **reads** the current bag and **returns only the fields it wants to change**:

```python
def route(state: DeskState) -> dict[str, str]:
    return {"path": "refund"}   # merge this in; leave everything else alone
```

After `route`, the case file still has the email and ticket id. It now also has `path="refund"`.

Starting contents come from `ticket_input()` — the ticket id, the email block, and the policy text shown to the model. Everything else is empty until a node fills it in.

| Field | What it is | Who writes it | `refund_day20` example |
| --- | --- | --- | --- |
| `ticket_id` | Which fixture | CLI / UI, at start | `"refund_day20"` |
| `condition` | `"clean"` or `"noisy"` (decoy in the prompt) | same | `"clean"` |
| `email_text` | Numbered email, shown to the model | start | `"[e-001] Hello, I purchased…"` |
| `policy_prompt` | Numbered policy the model is allowed to see | start | `"signed_policy\n[p-001] …thirty (30) days…"` |
| `path` | Ticket type | `route` | `"refund"` |
| `claims` | Cited facts from the two workers | `extract`, `playbook` | list of claim dicts, see below |
| `order_id` | `ORD-…` scraped from the email | `gather` | `"ORD-1001"` |
| `order_record` | JSON from disk, if a lookup ran | `lookup_order` | usually unset here (file exists) |
| `lookup_ran` | Did we spawn the extra lookup? | `lookup_order` | `false` |
| `verified` | Each claim plus pass/fail | `verify` | `[{claim, status: "grounded", …}]` |
| `scores` | Did those hits match the gold YAML? | `verify` | `{"extract:order_id": true, …}` |
| `approved` | Human yes/no on refunds | `approve` | `true` after you resume |
| `draft` | Customer-facing reply | `draft` | bullets built from grounded claims |

Three things people mix up:

1. **`DeskState`** — this ticket’s folder for *this* run. Claims, scores, draft, whether we paused.
2. **The span stores** — published email + canonical policy on disk. Source of truth. Read-only for the model.
3. **`fixtures/answers/{ticket}.yaml`** — the gold key used only by `verify` / `score`. Workers never see expected verdicts or acceptable span ids. They get the *questions* only.

When the graph is checkpointed to sqlite, it is `DeskState` that gets saved. Not the policy files.

### A claim is one cited fact

A **claim** is not the final email. It is one assertion the model is willing to stand behind, with a footnote.

```python
class Claim(BaseModel):
    statement: str          # the fact, in the worker's words
    span_id: str            # which line: "e-001" (email) or "p-001" (policy)
    quote: str              # exact substring copied from that line
    source: "email" | "policy" | None
    question_id: str | None # set by extract ("which order id?")
    rule_id: str | None     # set by playbook ("refund_window_30")
    verdict: "pass" | "fail" | None  # playbook only: does the rule hold?
```

`extract` answers fact questions from the email (and sometimes policy). One extract claim for this ticket looks like:

```json
{
  "statement": "The customer gave order ORD-1001.",
  "span_id": "e-001",
  "quote": "ORD-1001",
  "source": "email",
  "question_id": "order_id"
}
```

That means: “I claim the order id is ORD-1001, and I copied that string from email line `e-001`.”

`playbook` applies a policy rule and says pass or fail. One playbook claim looks like:

```json
{
  "statement": "Day 20 is still inside the 30-day refund window.",
  "span_id": "p-001",
  "quote": "thirty (30) days",
  "source": "policy",
  "rule_id": "refund_window_30",
  "verdict": "pass"
}
```

That means: “Rule `refund_window_30` passes, and I am citing the thirty-day sentence, not the fourteen-day decoy.”

The desk wants **a list of these**, not a paragraph. `verify` can check each one with no model: does `span_id` exist, and is `quote` actually in that line of the *canonical* store? If the model quotes `"fourteen (14) days"` under `p-001`, the quote does not match canonical `p-001` (that line says thirty). Status becomes `ungrounded`. If that wording lives only in `decoy_14_day.txt`, `decoy_match` is set to `draft_policy` so you can see the trap fire.

`draft` never invents new facts. It prints the `statement` of every claim whose status is `grounded`, or it refuses.

So the split is:

```
workers  →  claims          (cited facts, maybe wrong)
verify   →  verified        (those facts, stamped grounded / ungrounded)
score    →  scores          (did the grounded hits match the gold key?)
draft    →  draft           (reply text built only from grounded claims)
```

`claims` stays on state after verify. `verified` is a new list: each item wraps a claim with `status`, `reason`, `decoy_match`, and `task` (`extract` vs `playbook`).

### Why two workers both write `claims`

After `route`, **both** `extract` and `playbook` run. Each returns `{"claims": […]}`.

LangGraph’s default merge is **overwrite**. If both write the same field, the second one wins and the first list vanishes. That is why `claims` is declared as:

```python
claims: Annotated[list[dict], operator.add]
```

`operator.add` on lists means **concatenate**. Extract’s two facts and playbook’s two facts become one list of four. `draft` and `verified` stay overwrite: there should be one of each per run.

If you drop that annotation, you get the fan-in bug: one worker’s output disappears and LangGraph will not warn you.

### The walk, field by field

```
START → route → extract ∥ playbook → gather → lookup? → verify → approve → draft → END
```

1. **`route`** reads `email_text`, writes `path` (`refund` / `how_to` / `bug`). Keywords only. It does not decide the refund.
2. **`extract`** and **`playbook`** call the model. They only write `claims`. They do not pick the next node. They do not mint a thread id.
3. **`gather`** waits until both workers have finished, then writes `order_id` if the email contains `ORD-…`.
4. **`lookup_order`** runs only when that id has no file under `fixtures/orders/`. It writes `order_record` (`found: false` for `ORD-9999`). `refund_day20` has `ORD-1001.json` on disk, so this node is skipped.
5. **`verify`** is code. It reads `claims` plus the canonical stores (and the decoy only to *label* a bad quote). It writes `verified` and `scores`.
6. **`approve`** reads `path`. Refunds call `interrupt()` and wait. How-to and bug set `approved=True` and continue.
7. **`draft`** reads `verified` and `approved`. Writes `draft`. Then `END`.

That is the whole program. The rest of this section is the LangGraph vocabulary for the same walk.

---

## LangGraph primitives this desk uses

You assemble a `StateGraph(DeskState)`, add nodes and edges, then `compile()`. Compile attaches the checkpointer and rejects orphaned nodes. You cannot `invoke` the builder.

**Nodes** are functions `(state) -> update`. **Edges** decide who runs next. Nodes do the work; edges are the control plane. A worker that returned `Command(goto=…)` would be sitting in that plane — extract and playbook are not allowed to.

| Node | Kind | Writes on DeskState |
| --- | --- | --- |
| `route` | Classifier | `path` |
| `extract`, `playbook` | Live model workers | `claims` (appended) |
| `gather` | Fan-in wait | `order_id` |
| `lookup_order` | Code, only if the order file is missing | `order_record`, `lookup_ran` |
| `verify` | Code, no model | `verified`, `scores` |
| `approve` | Control; may `interrupt()` | `approved` |
| `draft` | Code | `draft` |

`gather` is a node but not a “unit of work” in the docs sense. It exists so both workers finish before the next edge runs.

**`START` / `END`** are the entry and the stop. `add_edge("verify", "approve")` is a fixed hop. `after_gather` is a **conditional edge**: it reads state and returns either `"verify"` or a `Send` to `lookup_order`.

A **super-step** is one tick: every ready node runs, then a checkpoint is written. `extract` and `playbook` have no data dependency on each other, so they run in the **same** tick. `verify` needs their claims, so it runs in a **later** tick. If one sibling raises, that tick’s updates are not committed. Resume after a crash is from a super-step boundary, not from the middle of a node.

**Fan-out / fan-in:** two edges leave `route` (static fan-out). Fan-in is just “a node whose incoming edges are all satisfied” — here, `gather`. The reducer on `claims` is what makes the join lossless.

**`path`** is exclusive choice (`refund` / `how_to` / `bug`). Today both workers still run so the fan-out stays visible. `path` is on state so a later change can send only one specialist without moving the stores or `verify`. A misroute is a control-plane error, not a “dumb extract.”

**`Send("lookup_order", {order_id, …})`** creates a task at **runtime** when the units were not all known at compile time. The payload *is* the state that node sees. Output reduces back into the **same** thread. It is not `threads.create`.

A **thread** is one case walking the compiled graph, keyed by `thread_id` in `{"configurable": {"thread_id": "T-2041"}}`. It is not an OS thread and not a worker. Two tickets are two ids on one compiled graph. The CLI (or the UI) mints the id. Reusing it loads the last checkpoint; a new id starts empty.

The **checkpointer** (`SqliteSaver` at `.data/tickets.sqlite`) snapshots `DeskState` after each super-step. That is short-term run memory: where the ticket is, what claims exist, whether we are waiting on approve. It is not the policy store. LangGraph’s cross-thread Store is a different object and is not used here.

- Isolation: `T-2041` and `T-2042` do not share claims.
- Resume: same id after interrupt or process restart.
- History: `get_state().next` / `get_state_history` (`--status`).
- Fault tolerance: pending writes from a sibling that finished in a failed super-step.

Refunds call `interrupt({…})` inside `approve`. The graph stops, the payload comes back on `__interrupt__`, and `next` is `approve`. Resume is `Command(resume="approve"|"reject")` on the **same** `thread_id`. The node restarts from the top of `approve`; `interrupt()` then returns the resume value instead of pausing. `--skip-approval` compiles without that pause.

`Command` as **input** to `invoke` is only for `resume` here. Do not pass `Command(goto=…)` from extract.

```python
graph = builder.compile(checkpointer=saver)
graph.invoke(ticket_input(...), {"configurable": {"thread_id": tid}})
graph.get_state(config).next    # queued node names
graph.get_state_history(config) # checkpoints for that thread
```

`invoke` with a full `ticket_input` starts (or restarts) a walk. `invoke` with `Command(resume=…)` continues a paused one. Mixing those two is how you accidentally re-run extract on an already-verified ticket.

Workers do not start threads. There is no lead agent. For the legal-document experiment with the same split (canonical store, decoys, parallel tasks), see lexorchestra.