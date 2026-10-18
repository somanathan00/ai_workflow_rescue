# Intent

## Problem
Order workflows that touch external systems fail in ways that are hard to recover from safely.
The dangerous case is not an outage, it is ambiguity: an operation succeeds but the caller never
hears back. Retrying blindly duplicates side effects; giving up leaves work stuck; and a person
paged at night has to reconstruct what happened from scattered logs.

## What this project is for
A backend that:

1. Preserves a complete history of every workflow.
2. Retries automatically only when the failure is known to be safe to repeat.
3. Stops when the outcome is uncertain, and verifies reality before continuing.
4. Gathers evidence from the database and uses an LLM to explain the likely cause and recommend a
   next step.
5. Treats that recommendation as advice: deterministic policy and a human approval decide
   whether anything runs.
6. Resumes without creating duplicate reservations or invoices, and records every decision.

## What it deliberately is not
- Not an autonomous agent. The AI has no tool that changes state and no path to execute recovery.
- Not a distributed system of many services. One database and one codebase keep the consistency
  guarantees simple to state and demonstrate.
- Not a real inventory or billing system. The external provider is simulated so ambiguous
  failures can be reproduced on demand.

## Success criteria
- `SIM-RECOVER` finishes after two recorded failures; `SIM-TRANSIENT` exhausts its budget;
  `SIM-PERMANENT` fails without retrying.
- After a lost response, reconciliation finds the original reservation and the workflow
  completes with exactly one reservation and one invoice.
- An order is accepted and eventually processed even if Redis is down when it is created.
- A recovery can be requested, approved by someone else, durably queued, executed once, and
  audited.
- An unsafe model recommendation is downgraded before anyone can act on it, and the system
  recovers fine with no model at all.
