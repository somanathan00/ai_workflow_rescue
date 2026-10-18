# Architecture

AI Workflow Rescue processes orders through a three-step workflow, recovers from failures
automatically where that is provably safe, and otherwise routes the failure to a human with
AI-assisted analysis. It is a modular monolith (see `decisions/001-modular-monolith.md`).

```
Validate order -> Reserve inventory -> Generate invoice
```

## Components

| Component | Technology | Responsibility |
|---|---|---|
| API | FastAPI | Auth, orders, workflows, recovery, investigations, health, metrics |
| Database | PostgreSQL 16 | All durable state: business data, workflow events, outbox, leases |
| Broker | Redis | Celery task delivery only; nothing durable lives here |
| Workflow worker | Celery (`workflow`, `investigations` queues) | Runs workflows, recoveries, investigations |
| Beat | Celery Beat | Periodic sweeps (overdue retries, stale recovery leases) |
| Outbox dispatcher | `app.workers.outbox_runner` | Publishes committed outbox messages to Celery |
| Investigator | LangGraph + Gemini | Read-only analysis that produces an advisory recommendation |
| Web UI | React + TypeScript, served by nginx | Operator and admin console; nginx also proxies `/api` to the API (single origin, no CORS) |

## Request flow

```
POST /orders
  one transaction: order + workflow + workflow_created event + outbox(workflow.start)
  -> 201                                    (no Redis call on the request path)
outbox dispatcher -> Celery process_order -> WorkflowService.process
```

## Workflow execution (`WorkflowService`)

- **Claim.** `_claim` takes the workflow row lock, moves `pending`/`retry_scheduled` to
  `processing`, increments `attempts` and commits *before* any step runs. `attempts` therefore
  counts claimed executions in the current processing cycle, and a failing step cannot roll the
  counter back.
- **Steps.** Each step runs in its own short transaction under `SELECT ... FOR UPDATE`.
  A redelivered task finds `current_step` already advanced and continues from there.
- **Reserve inventory** is the only step with an external side effect, so it is split into three
  transactions (prepare + lease, provider call with no lock held, settle). See below.

### Retries

`RetryPolicy` allows 3 executions in total with delays of 2s then 4s (jitter in production).
Only `TransientWorkflowError` retries. `PermanentWorkflowError` fails immediately,
`UncertainOutcomeError` goes to `needs_review`, anything unexpected goes to `needs_review`.

On a retryable failure `record_failure` sets `retry_scheduled` and `next_retry_at` in PostgreSQL,
then the task schedules a Celery countdown. The countdown is a convenience, not the guarantee:
the `requeue_due_retries` sweep re-enqueues anything overdue, and `process` only claims a retry
that is due and still scheduled, so duplicates are harmless.

### Uncertain outcomes

A side effect may commit while its response is lost. `WorkflowOperation` records each
side-effecting operation under a stable key (`reserve:<order_id>`) reused on every attempt:

1. **Prepare**: lock workflow, create/load the operation, take a lease (`claim_token`,
   `claim_expires_at`).
2. **Provider call**: no transaction or row lock is held. The provider is idempotent per order.
3. **Settle**: only the lease holder may confirm the operation or mark it `uncertain`.

On `UncertainOutcomeError` the operation becomes `uncertain` and the workflow `needs_review`.
The worker never calls the provider again. `ReconciliationService` verifies the reservation
against the original order; a matching one confirms the operation and resumes at
`generate_invoice`. A missing record is *not* treated as proof the operation never ran.

## Recovery (`RecoveryService`)

State machine: `requested -> approved -> queued -> executing -> executed | failed`, plus
`requested -> rejected`. `RecoveryPolicy` is a deterministic allow-list checked at request,
approval, queueing and again at execution against live workflow state.

| Action | Allowed when |
|---|---|
| `retry_workflow` | workflow `failed` with `TRANSIENT_ERROR`; grants one extra execution, never resets the retry budget |
| `reconcile_and_resume` | workflow `needs_review` with `UNCERTAIN_OUTCOME` at `reserve_inventory` |
| `mark_for_review` | workflow `failed` or `needs_review` |
| `release_reservation` | workflow `failed` or `needs_review` and a reservation exists (`reserved`, or `released` so a crashed run can finish) |

Authorization: operators request recovery on their own workflows; only admins approve or reject;
nobody approves their own request. A partial unique index allows one active recovery per workflow.
Execution is queued through the outbox and performed by a worker holding a lease, so a crashed
worker's action is reclaimed by `reclaim_stale_recoveries`.

### Compensation (undoing a side effect)

If an order fails *after* its stock was reserved (for example a permanent invoicing failure), the
reservation would stay held for an order that can never complete. `release_reservation` is the
compensating recovery: it goes through the normal request, approval and execution path, and is
never automatic.

Execution mirrors the reserve step, in three short transactions: prepare (record a
`release:<order_id>` operation), call the provider with no lock held (`release` is idempotent),
then settle. Settling sets the reservation operation to `failed/COMPENSATED`, the workflow to
`compensated` and the order to `cancelled`. `compensated` is terminal: no further recovery is
offered. A run that crashes after the provider released the stock is simply repeated.

`GET /workflows/held-stock` and the `held_reservations` metric list failed or in-review workflows
that still hold stock, oldest first, so held inventory is visible rather than discovered later.

## Transactional outbox

`OutboxPublisher.add` writes a message inside the caller's transaction, so it exists if and only
if the state change commits. `OutboxDispatcher` claims batches with `FOR UPDATE SKIP LOCKED`
and a claim lease, publishes with no transaction open, then marks `published`. Failures back off
exponentially (capped at 60s); unknown event types are marked `dead`. Delivery is at-least-once,
so every consumer is idempotent. Routing uses a fixed allow-list of event types:
`workflow.start`, `workflow.resume`, `recovery.execute`, `investigation.start`.

## AI investigator

`POST /workflows/{id}/investigate` creates a pending `Investigation` and queues it. The LangGraph
graph is `load_workflow -> collect_evidence -> (analyze | nothing_to_recover) -> validate`.

- Evidence comes only from read-only, database-backed tools. Every fact carries a stable `ref`.
- The prompt marks logs and errors as untrusted and bounds/cleans every string.
- Gemini returns a Pydantic-validated `InvestigationResult` (temperature 0).
- `apply_guardrails` can only make the recommendation safer. It downgrades when the model cites
  evidence that was not supplied, has low confidence, proposes a retry over an existing side
  effect, proposes reconciliation without a matching reservation, or violates recovery policy.
- The recommendation is advisory. It becomes action only through the recovery APIs, which
  re-validate everything and require admin approval. The system recovers safely without Gemini.

## Measuring the AI

Three independent views, because model confidence is not evidence of usefulness:

- **Offline evaluation** (`app/agents/evaluation.py`, `make eval-offline`): ten frozen scenarios,
  each with acceptable and unsafe actions. Every action is fed to the guardrails as a bad model
  answer (with real or invented evidence, high or low confidence). Nothing unsafe may get through.
- **Live evaluation** (`make eval`): the same scenarios against the real model. Reports raw
  accuracy, accuracy after guardrails, unsafe suggestions and how many the guardrails rescued.
- **Outcome metrics** (`GET /investigation-metrics`, the AI quality page): of the advice that
  suggested an action, how much was followed, approved, executed and actually worked; how often
  people chose a different action; the guardrail downgrade rate; and confidence versus outcome.
  People can also rate each investigation helpful or not helpful (`investigation_feedback`).

## Data model

`users`, `orders`, `workflows`, `workflow_events` (append-only audit log), `workflow_operations`,
`inventory_reservations`, `invoices`, `workflow_recovery_actions`, `investigations`,
`outbox_messages`, `investigation_feedback`. Status and role columns are guarded by `CHECK` constraints derived from
`app/domain/enums.py`; constraint names follow a fixed naming convention.

## Observability

JSON logs on every service (`app/core/logging.py`), tagged with `workflow_id` so one workflow can
be followed across API, worker, outbox and investigator. `/health/live`, `/health/ready`
(Postgres required, Redis reported) and `/metrics` (Prometheus text derived from PostgreSQL:
workflow/outbox/recovery/investigation counts, oldest pending outbox age, Gemini tokens and
latency). Container healthchecks cover API, worker and outbox.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Connections |
| `JWT_SECRET_KEY` | Required; production refuses a short or default value |
| `ENVIRONMENT` | `development`/`test` enable failure injection; `production` enables jitter and strict checks |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS` | Investigator; the key is optional |
