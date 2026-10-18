# AI Workflow Rescue

An order-processing backend that recovers from failures it can prove are safe to recover from,
and hands everything else to a human with an AI-assisted investigation.

```
Validate order -> Reserve inventory -> Generate invoice
```

The interesting case: inventory is reserved, but the response is lost. A naive retry would
reserve twice. Here the workflow stops, the reservation is verified against the original order,
and the workflow resumes without creating a duplicate reservation or invoice.

**Stack:** FastAPI, PostgreSQL, Redis, Celery, SQLAlchemy, Alembic, LangGraph, Gemini (backend); React, TypeScript, Vite, nginx (frontend).

## Quick start

Requires Docker with Compose, and GNU Make.

```sh
make up        # build and start everything: UI, API, worker, beat, outbox dispatcher, Postgres, Redis
make seed      # create an admin and a dev operator (dev credentials are printed)
make scenarios # run every failure scenario through the API
make demo      # uncertain-outcome recovery, end to end
```

Then open **http://127.0.0.1:3000** and sign in as `operator` (or `admin`) with the credentials `make seed` prints.
API docs: http://127.0.0.1:3000/docs (or http://127.0.0.1:8001/docs). `make` lists all commands. `make down-volumes` also
deletes the database.

For real use, set `JWT_SECRET_KEY`, `ENVIRONMENT=production` and `ADMIN_PASSWORD` (see
`.env.example`). Production refuses a weak secret. Failure injection only runs in
`development`/`test`.

### AI investigation

Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) in your environment before `make up`, then:

```sh
make demo DEMO_ARGS=--investigate
```

Without a key the app runs normally; investigations are marked `failed` with the reason and
recovery is unaffected.

**Gemini free tier:** the free tier allows only about 20 requests per model per day. One
investigation is one request, and `make eval` uses about 8, so you can hit the limit quickly.
When that happens the investigation shows a 429 error and recovers by itself the next day (or use a
billed key).

### Is the AI any good? (evaluation)

```sh
make eval-offline   # no key needed: throws every kind of bad answer at the guardrails
make eval           # asks the real model about 10 fixed scenarios (uses ~8 API requests)
```

Both report accuracy, how often the model suggested something unsafe, and whether anything unsafe
got past the guardrails (that must be 0). `make eval` exits non-zero if it could not evaluate every
scenario, so an incomplete run never looks like a pass. In the UI, the **AI quality** page (admin)
measures what people actually did with the advice, and every investigation has 👍/👎 buttons.

## The web UI

| Page | Who | What it does |
|---|---|---|
| Dashboard | everyone | Counts by status, what needs attention, pending approvals (admin) |
| Orders | everyone | Place orders (one-click failure scenarios), see each order's workflow |
| Workflows / detail | everyone | Live step progress, retry countdown, audit trail, **Investigate with AI**, request/approve/execute recoveries |
| Approvals | admin | Inbox of recovery requests across all workflows |
| AI quality | admin | Whether the AI is useful: advice acted on, recoveries that worked, helpfulness ratings, guardrail activity, confidence vs. outcome |
| System | everyone | Dependency health, outbox backlog, stock held by failed orders, activity counts, AI token usage |

Operators see their own orders and workflows; admins see everything and are the only ones who can
approve or reject a recovery (never their own request). The UI mirrors the backend recovery policy
to explain why an action is unavailable, but the backend re-validates every request.

## How it stays correct

| Concern | Mechanism |
|---|---|
| Lost task delivery | Transactional outbox; the order commits together with its message |
| Transient failures | Bounded retries (3 executions, 2s/4s backoff) persisted in PostgreSQL, with a sweep as the safety net |
| Ambiguous side effects | Stable operation keys, leases, an idempotent provider, reconciliation before any resume |
| Duplicate delivery | Row locks, leases, terminal-state checks, unique constraints per order |
| Unsafe recovery | Deterministic policy re-checked at every step; admin approval; one active recovery per workflow |
| Unsafe AI advice | Read-only evidence tools, schema validation, guardrails that only downgrade, advisory only |
| Stock held for orders that can't finish | Compensation: an approved `release_reservation` returns the stock and closes the order as `compensated` |
| Knowing if the AI helps | Fixed-scenario evaluation, per-investigation feedback, outcome metrics |

Details: [`docs/architecture.md`](docs/architecture.md), [`docs/api.md`](docs/api.md),
[`docs/failure_scenarios.md`](docs/failure_scenarios.md), [`docs/decisions/`](docs/decisions/).

## Failure scenarios

| `product_id` | Result |
|---|---|
| `LAPTOP-001` | `completed` |
| `SIM-RECOVER` | fails twice, `completed` on attempt 3 |
| `SIM-TRANSIENT` | `failed` after the retry budget |
| `SIM-PERMANENT` | `failed`, no retry |
| `SIM-UNCERTAIN` | reservation committed, `needs_review`, recoverable via reconciliation |
| `SIM-INVOICE-FAIL` | invoice fails after stock was reserved, `failed`; the stock is released by a compensation |

## Operations

- `GET /health/live`, `GET /health/ready`, `GET /metrics` (Prometheus text, internal use).
- JSON logs on every service, tagged with `workflow_id`: `make logs`, `make logs-outbox`.
- `make lint` runs Ruff; CI (`.github/workflows/ci.yml`) lints, applies migrations, checks that
  models match migrations, runs the tests and builds the image.
- Host ports bind to `127.0.0.1`: UI 3000, API 8001, Postgres 5433, Redis 6380
  (`FRONTEND_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT` override).
- The UI container (non-root nginx) serves the app and proxies `/api`, `/health`, `/metrics` and
  `/docs` to the API, so the browser uses a single origin and no CORS is needed.
- Frontend development with hot reload: `cd frontend && npm install && npm run dev`
  (proxies to the API on port 8001).

## Layout

```
backend/
  app/
    api/          routers and auth dependencies
    services/     business logic (workflow, recovery, reconciliation, investigation, orders)
    domain/       enums, error types, retry and recovery policies
    models/       SQLAlchemy models (app/models/__init__.py)
    agents/       LangGraph investigator, evidence tools, prompt, guardrails
    infrastructure/  database session, Gemini client, outbox publisher/dispatcher
    workers/      Celery app and tasks, outbox runner
  alembic/        migrations       scripts/   seed and scenario/demo drivers
  Dockerfile  requirements.txt  pyproject.toml
frontend/
  src/            React app (pages, components, API client)
  Dockerfile  nginx.conf
docker-compose.yml  Makefile  .env(.example)
docs/             architecture, API, scenarios, decisions
```

## Known limitations

- The automated test suite has not been written yet; behaviour was verified by running the
  scenarios and demo against the stack, and the UI by driving it in a headless browser.
- The inventory provider is simulated; a real integration would pass the operation key as the
  provider's idempotency key and reconcile through its API.
- Gemini integration is verified up to the API call; it has not been exercised against a live key.
- Login has no rate limiting, and `/metrics` is unauthenticated (it is also reachable through the UI's nginx).
- The UI stores its access token in `localStorage`; a hardened deployment would use an httpOnly cookie.
- Several scaffold files from the initial layout (`app/models/*.py` per-table files,
  `app/repositories/*`, `app/domain/entities/*`, `app/infrastructure/cache/redis_client.py`)
  are intentionally empty; models live in `app/models/__init__.py`.
