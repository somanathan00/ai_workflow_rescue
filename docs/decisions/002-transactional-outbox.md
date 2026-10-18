# 002: Transactional outbox for task delivery

**Status:** accepted

## Context
Committing an order and then calling `apply_async` leaves a window where the order exists but no
task was ever queued (crash or Redis outage between the two steps).

## Decision
Services write an `outbox_messages` row in the same transaction as the state change. A dedicated
dispatcher process polls PostgreSQL (not Celery Beat, so it does not depend on Redis to schedule
itself), claims batches with `SKIP LOCKED` plus a claim lease, publishes with no transaction
open, and records the result. Event types are routed through a fixed allow-list.

## Consequences
- Delivery is at-least-once; all consumers (`process_order`, `execute_recovery`,
  `run_investigation`) are idempotent and lease-guarded.
- `POST /orders` no longer needs Redis.
- Failed publishes back off exponentially (cap 60s) and are never dropped; only unknown event
  types are dead-lettered.
- Latency is bounded by the poll interval (1s).
