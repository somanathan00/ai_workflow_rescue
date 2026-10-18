# 001: Modular monolith

**Status:** accepted

## Context
The system has an API, background workflows, a recovery process and an AI investigator. Splitting
these into services would add network boundaries that make the hardest property, consistent
recovery from partial failure, harder to reason about and demonstrate.

## Decision
One codebase and one PostgreSQL database, deployed as several processes from one image
(`api`, `worker`, `beat`, `outbox`). Layers are kept separate: `api` -> `services` ->
`models`/`domain`, with `workers` and `agents` as entry points.

## Consequences
- Workflow state, events, outbox rows and recovery actions share a transaction, which the outbox
  and the recovery state machine rely on.
- The AI investigator is a read-only module, not a service with its own write path.
- Scaling is horizontal per process type. Extracting a service later is possible because
  cross-module calls go through service functions and the outbox.
