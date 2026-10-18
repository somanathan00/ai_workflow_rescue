# 004: Compensation is an approved recovery, not an automatic cleanup

**Status:** accepted

## Context
An order can fail after its inventory was reserved. The stock then stays held for an order that
will never finish. Releasing it automatically on failure is tempting, but a failure is not always
final: an `UNCERTAIN_OUTCOME` may still be reconcilable, and a transient failure may still succeed
on a retry. Releasing too early destroys work that could have been saved.

## Decision
- Compensation is a normal recovery action, `release_reservation`, with the same request,
  admin approval and queued execution as every other recovery.
- The policy only allows it for failed or in-review workflows that actually have a reservation.
  The AI guardrails additionally require that the reservation matches the order, so a missing or
  conflicting reservation (possibly someone else's stock) is never released.
- Held stock is made visible instead of silently fixed: `GET /workflows/held-stock`, the
  `held_reservations` metrics, a dashboard banner and a warning on the workflow page.
- The provider's `release` is idempotent and runs outside any transaction, like `reserve`, so a
  crashed run is repeated safely. `compensated` is a terminal workflow status (the order becomes
  `cancelled`) so nothing can be retried or released twice.

## Consequences
- A person decides between saving the order (retry or reconcile) and giving up (release).
- Stock can stay held until someone acts; the metrics and banner exist to make that cost visible.
- Automating low-risk releases later (for example permanent failures after the invoice step) is a
  policy change on top of this, not a redesign.
