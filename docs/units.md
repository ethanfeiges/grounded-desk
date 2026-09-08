# Units

A unit of work has an id, an input schema, an output schema, and a postcondition. In this repo every unit is a node. Not every node is a unit: `gather` waits for the fan-in, and `after_gather` is an edge function.

## route

- **Input:** raw email text.
- **Output:** `path` ∈ {`refund`, `how_to`, `bug`}.
- **Postcondition:** value is in that set.
- **Resource:** `router.classify` (keywords). An LLM classifier can replace the function without changing the graph if it still returns only a path.

This is a control-plane step, not a support answer. Do not put refund verdicts here.

## extract

- **Input:** ticket email, published policy block, and public questions (id + question only).
- **Output:** `Claim[]` with `question_id`, `span_id`, `quote`.
- **Postcondition:** quote exists on that span in the email or canonical policy store.
- **Resource:** live `LangChainWorker`. The plane passes `public_items`. Must not call `invoke` with a new thread.

Several questions in one call are still one unit. The questions are cases inside the work item.

## playbook

- **Input:** same ticket.
- **Output:** `Claim[]` with `rule_id` and `verdict`.
- **Postcondition:** grounded, and `verdict` matches `fixtures/answers/{ticket}.yaml`.

## lookup_order

- **Input:** `order_id` from a `Send` payload.
- **Output:** `order_record` (`found` true/false).
- **Postcondition:** if the json file exists under `fixtures/orders/`, `found` is true; otherwise false.
- **When it runs:** only if `after_gather` cannot find that id on disk. That is runtime work creation, not a new thread.

## verify

- **Input:** accumulated claims plus the two canonical stores.
- **Output:** `VerifiedClaim[]` and task scores.
- **Postcondition:** implemented in `verify.py`. No model.

## approve

- **Input:** `path`, scores, ticket id.
- **Output:** `approved` true/false.
- **Postcondition:** refunds pause at `interrupt()` until the CLI resumes the same `thread_id`. Other paths set `approved=True` and continue.
- **Resource:** control plane. Not a worker.

## draft

- **Input:** verified claims, optional `order_record`, `approved`.
- **Output:** reply text.
- **Postcondition:** every bullet is a grounded statement, the “cannot confirm” fallback, or “Refund was not approved” when `approved` is false.
