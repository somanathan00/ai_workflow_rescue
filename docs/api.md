# API reference

Base path `/api/v1`. Interactive docs at `/docs`. Authenticate with
`Authorization: Bearer <token>` from `POST /auth/login`.

Roles: `operator` (default) and `admin`. Operators only see their own orders and workflows;
admins can act on any workflow. A missing or foreign resource always returns `404`.

## Auth

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | `{username, email, password}`; username `[a-z0-9_]{3,30}`, password 12-128 chars; always creates an `operator` |
| POST | `/auth/login` | Form fields `username` (username **or** email) and `password` |
| GET | `/auth/me` | Current user |

Create the first admin with `make seed`.

## Orders

| Method | Path | Notes |
|---|---|---|
| POST | `/orders` | Requires `Idempotency-Key` header; `{product_id, quantity 1-1000}`. `201` for a new order, `200` when the key was already used with the same body, `409` if used with a different body. Does not depend on Redis. |
| GET | `/orders` | Own orders newest first (admins: all); `limit`, `offset`; includes `workflow_id` and `workflow_status` |
| GET | `/orders/{id}` | Own orders |

## Workflows

| Method | Path | Notes |
|---|---|---|
| GET | `/workflows` | Own workflows newest first (admins: all); optional `status`, `limit`; includes `product_id`, `quantity` |
| GET | `/workflows/{id}` | Status, `current_step`, `attempts`, `next_retry_at`, last error |
| GET | `/workflows/{id}/events` | Ordered audit log (max 500) |
| GET | `/workflows/failed` | Own failed workflows |
| GET | `/workflows/held-stock` | Failed or in-review workflows that still hold reserved stock (own; admins: all), oldest first |
| POST | `/workflows/{id}/reconcile` | Direct reconciliation of an uncertain reservation (owner). `409` unless the workflow is `needs_review` at `reserve_inventory` with an uncertain operation, and `409` if the reservation conflicts with the order. Idempotent. |

## Recovery actions

| Method | Path | Who | Result |
|---|---|---|---|
| POST | `/workflows/{id}/recovery-actions` | owner/admin | `201` `requested`. Body `{action_type, reason (10-1000), investigation_id?}`; optional `Idempotency-Key` |
| GET | `/workflows/{id}/recovery-actions` | owner/admin | History |
| POST | `.../{action_id}/approve` | admin, not the requester | `approved` |
| POST | `.../{action_id}/reject` | admin | `rejected`; body `{reason}` |
| POST | `.../{action_id}/execute` | owner/admin | `202`, `queued`; repeating is a no-op |
| GET | `/recovery-actions` | owner/admin | Cross-workflow queue, e.g. `?status=requested` (admins: all; operators: their own workflows) |

`action_type`: `retry_workflow`, `reconcile_and_resume`, `mark_for_review`, `release_reservation`
(releases the order's reserved stock and closes it as `compensated`; needs a failed or in-review
workflow with a reservation).
Status: `requested`, `approved`, `rejected`, `queued`, `executing`, `executed`, `failed`.

Common errors: `409` policy refusal, a second active recovery, wrong state, mismatched
`investigation_id`; `403` non-admin approval or self-approval.

## Investigations

| Method | Path | Notes |
|---|---|---|
| POST | `/workflows/{id}/investigate` | `202`; returns the pending investigation, or the one already in flight |
| GET | `/workflows/{id}/investigations` | Newest first |
| PUT | `/investigations/{id}/feedback` | Body `{rating: "helpful" \| "not_helpful", comment?}`. One verdict per person; sending again replaces it. Your own verdict comes back as `my_feedback` |
| GET | `/investigation-metrics?days=30` | Admin only. Outcome funnel, guardrail activity, confidence vs. outcome, feedback, cost |
| GET | `/investigations/{id}` | Result: `root_cause`, `reasoning`, `recommended_action`, `confidence`, supported `evidence`, `policy_result` (what the model said vs. what guardrails allowed), token usage |

`recommended_action` is one of `retry_workflow`, `reconcile_and_resume`, `mark_for_review`,
`release_reservation` or `no_action`, and is advisory. Pass the investigation's `id` as `investigation_id` when
requesting recovery; the requested action must equal the recommendation.

## Operations

| Path | Notes |
|---|---|
| `GET /health/live` | Process is up |
| `GET /health/ready` | `503` if PostgreSQL is unreachable; Redis reported only |
| `GET /metrics` | Prometheus text format; aggregate counts only, keep it internal |
