# Grounded Desk

A support desk that is allowed to answer only from a published policy and the ticket email. The model can be shown a decoy policy. The checker cannot.

I built this to practice LangGraph the way a workflow engine actually works: units of work, a control plane that owns scheduling, and a store nobody on the model side can edit. The public research repo for the heavier version of this idea is still [lexorchestra](https://github.com/ethanfeiges/lexorchestra). This one is the small, transferable copy.

## What a ticket run does

```
route → extract ∥ playbook → gather → (lookup if the order is missing) → verify → draft
```

- **route** is a keyword function. It returns `refund`, `how_to`, or `bug`. It is not a support answer.
- **extract** and **playbook** are workers. They return `Claim` JSON (span id + quote). They run in the same super-step. Claims land on one list through an `operator.add` reducer. Drop the reducer and one of them will vanish.
- **verify** is Python. A claim is grounded only if the quote is in the canonical email or policy store. A 14-day quote from the draft policy is a miss, even when the span id looks right.
- **draft** may use grounded claims only. If nothing grounded, it says so.
- **lookup_order** runs only when the email cites an `ORD-*` that is not on disk. That is the one place the graph creates work at runtime (`Send`). Workers do not mint `thread_id`.

One ticket is one LangGraph thread. The CLI sets `configurable.thread_id`. A second ticket is a second thread on the same compiled graph.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest
```

## Run a fixture

```powershell
grounded-desk refund_day20
grounded-desk refund_day20 --condition noisy --worker decoy
grounded-desk missing_order
```

`--worker decoy` is the dishonest model: it cites the 14-day draft. Use it to watch verify fail `refund_window_30`. `--condition noisy` is what that model would have seen in the prompt.

Tickets live under `fixtures/emails/`. Gold for scoring is `fixtures/answers/{ticket_id}.yaml`. The published policy is `fixtures/policies/canonical.txt`. The trap is `fixtures/policies/decoy_14_day.txt`.

## Default worker

Tests and the CLI use `MockWorker`. It is a scripted stand-in for an isolated model call so the graph and the verifier can be exercised without an API key. The node functions do not care; swap the object if you wire a real chat model later.

## Layout

```
grounded_desk/     graph, stores, verifier, mock worker
fixtures/          emails, policies, answer keys, one known order
docs/              units and how the graph is supposed to be read
tests/
```

## What this is not

There is no lead agent chatting with other agents. extract does not start threads. There is no live mail server. If you want the legal-document version of the same contract (canonical store, decoys, parallel tasks), that is lexorchestra.
