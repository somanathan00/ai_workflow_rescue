# Failure scenarios

Failure injection is keyed on `product_id` and only active when `ENVIRONMENT` is `development`
or `test`. Run all of them with `make scenarios`.

| Product | Behaviour | Final state | Attempts |
|---|---|---|---|
| `LAPTOP-001` | No failure | `completed` | 1 |
| `SIM-RECOVER` | Transient failure on executions 1 and 2, succeeds on 3 | `completed` | 3 |
| `SIM-TRANSIENT` | Always fails before reservation | `failed` after the retry budget | 3 |
| `SIM-PERMANENT` | Unsupported product | `failed`, no retry | 1 |
| `SIM-UNCERTAIN` | Provider commits the reservation, then the response is lost | `needs_review` | 1 |
| `SIM-INVOICE-FAIL` | Reserves stock, then the invoice step fails permanently | `failed` (stock held) | 1 |

The failure count for `SIM-RECOVER` derives from the persisted `attempts`, never from process
memory, so it behaves the same across any number of workers.

## Retry story (`SIM-RECOVER`)

```
workflow_started (attempt 1)
step_completed validate_order
step_failed reserve_inventory (attempt 1)   retry_scheduled (attempt 2, 2s)
retry_started (attempt 2)
step_failed reserve_inventory (attempt 2)   retry_scheduled (attempt 3, 4s)
retry_started (attempt 3)
step_completed reserve_inventory -> step_completed generate_invoice -> workflow_completed
```

## Uncertain-outcome story (`SIM-UNCERTAIN`)

```
reservation_requested
reservation_outcome_uncertain          workflow -> needs_review, reservation IS committed
investigation (optional)               advisory: reconcile_and_resume
recovery_requested -> recovery_approved (admin) -> recovery_queued
reconciliation_started -> reservation_confirmed -> reconciliation_completed
workflow_resumed -> recovery_executed -> workflow_completed
```

Exactly one reservation and one invoice exist at the end. `make demo` walks through this
(`DEMO_ARGS=--investigate` adds the AI step) and prints the SQL that proves it.

## Stuck-stock story (`SIM-INVOICE-FAIL`)

```
reservation_requested -> step_completed reserve_inventory      stock is RESERVED
step_failed generate_invoice (PERMANENT_ERROR) -> workflow_failed   the order can never complete
   the workflow page warns: "Stock is still reserved for this order"
investigation (optional)               advisory: release_reservation
recovery_requested -> recovery_approved (admin) -> recovery_queued
compensation_started -> reservation_released -> workflow_compensated -> recovery_executed
```

The reservation ends as `released`, the order as `cancelled` and the workflow as `compensated`
(terminal). Retrying is not offered: the failure is permanent. If the provider released the stock
but the worker crashed before recording it, executing the recovery again finishes the job.

## Infrastructure failures

| Failure | Behaviour |
|---|---|
| Redis down when an order is created | Order, workflow and outbox message commit; dispatcher retries with backoff and delivers after Redis returns |
| Redis down when a retry is scheduled | Workflow stays `retry_scheduled` in PostgreSQL; the sweep re-enqueues it |
| Worker dies after the provider committed | Operation lease expires; the next run reuses the operation key, the idempotent provider returns the existing reservation |
| Worker dies mid-recovery | Recovery lease expires; `reclaim_stale_recoveries` re-delivers it; execution is idempotent |
| Dispatcher publishes but crashes before marking | Message is published again; consumers tolerate duplicates |
| Gemini unavailable or no key | Investigation is marked `failed` with the reason; recovery is unaffected |
| Model recommends something unsafe | Guardrails downgrade it (recorded in `policy_result`) |
