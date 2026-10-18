# Write-up: AI Workflow Rescue

## Summary
AI Workflow Rescue is an order-processing backend (FastAPI, PostgreSQL, Redis, Celery) built
around one idea: **recover automatically only when it is provably safe, and make everything else
easy for a human to resolve**. An AI investigator (Gemini via LangGraph) explains failures and
recommends a recovery, but it never authorizes or executes one.

## The problem that shaped the design
Inventory is reserved, then the response is lost. The worker cannot tell whether the reservation
exists. Retrying may reserve twice; giving up strands the order.

## What I built

**Safe retries.** Transient failures retry up to three executions with 2s/4s backoff. State lives
in PostgreSQL (`retry_scheduled`, `next_retry_at`), not in Celery, and a periodic sweep
re-enqueues anything overdue. `SIM-RECOVER` derives its failures from the persisted attempt
count, so behaviour is identical across workers.

**Uncertain-outcome recovery.** Side effects are tracked as operations with stable keys and
leases. The provider call runs outside any workflow transaction, which is the only way to
simulate "committed but response lost" faithfully. On a lost response the operation becomes
`uncertain` and the workflow stops. Reconciliation verifies the reservation against the original
order and resumes at invoicing; absence of a record is never treated as proof of failure.

**Controlled recovery.** A state machine (`requested -> approved -> queued -> executing ->
executed|failed`) with admin-only approval, no self-approval, one active recovery per workflow
(enforced by a partial unique index) and policy re-checked at every step against live state.

**Reliable delivery.** A transactional outbox replaces "commit, then publish". Orders are
accepted while Redis is down and delivered when it returns. Delivery is at-least-once and every
consumer is idempotent.

**AI investigator.** A LangGraph pipeline collects evidence through read-only tools, asks Gemini
for a schema-validated analysis, then applies guardrails that can only downgrade the result.
Cited evidence must exist, confidence must clear a threshold, and a retry is refused where a side
effect already happened. The model's original answer and the guardrail verdict are both stored.

## Bugs found by running it, not by reading it
- The worker could not reach Redis because the host already ran Redis on 6379; the container
  silently never joined the network while the API still looked healthy.
- The first retry design incremented attempts inside the step's transaction, so a failing step
  rolled the counter back and retries would never end. Claiming an execution now commits first.
- Events written in one transaction shared a `created_at`, making the audit order ambiguous;
  events now use `clock_timestamp()`.
- A tight loop was possible when another worker held an operation lease; the reserve step now
  reports whether to continue.

## What I would do next
Write the automated test suite (the behaviours above were verified by running scenarios against
the stack, not by tests), exercise the investigator against a live model with a fixture dataset
of known failures, add rate limiting, and replace the simulated provider with a real integration
that uses the operation key as an idempotency key.

## Limitations
See the README. Notably: no automated tests yet, the Gemini call is untested live, the provider
is simulated, and `/metrics` is unauthenticated.
