# AI Workflow Rescue — starter scaffold

This is a **Day 1 scaffold**, not a finished workflow engine. The order endpoint currently returns a placeholder and does not persist or enqueue an order.

## Start with Docker

Install Docker Compose and GNU Make, then run:

```sh
make up
```

`make up` rebuilds the shared application image from the current source before starting the API, worker, database, and Redis. The API documentation is at http://127.0.0.1:8001/docs. `make down` stops the containers but preserves database data.

Run `make` to list the available commands. Common commands include `make status`, `make logs`, `make migrate`, and `make test`. `make down-volumes` also deletes the Postgres data volume.

For local Python development, create and activate a virtual environment, install `requirements.txt`, and run `uvicorn app.main:app --reload`. The Compose-managed services publish Postgres at `127.0.0.1:5433` and Redis at `127.0.0.1:6379`.

## Next milestones

- Day 1: database models, migrations, password hashing, JWT login, ownership checks.
- Day 2: Celery worker with Redis broker and persisted workflow events.
- Day 3: idempotency, unique reservation/invoice constraints, bounded retries.
- Day 4: AI investigator with structured output, evidence and policy gate.
- Day 5: tests, demo, real five-day log, quest documentation.

Keep secrets out of Git; `.env.example` is illustrative only.
