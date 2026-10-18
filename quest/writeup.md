# Write-up: AI Workflow Rescue

**In one sentence:** an order system that retries only when that is safe, stops and checks when it
cannot tell whether work was done, and uses an AI to explain failures, with a person approving
every fix.

## 1. The problem
An order has three steps: validate it, reserve inventory, create an invoice. Step 2 talks to another
system. Sometimes that system **does the work but the reply is lost**. The order system cannot tell
whether stock was reserved. Retrying might reserve twice. Giving up leaves the order stuck. Asking a
person means digging through logs.

A second, quieter problem: if the order then fails *after* stock was reserved, the stock stays held
for an order that will never finish.

## 2. What I built
- **Safe retries.** Temporary failures retry up to 3 times (waiting 2 s, then 4 s). The retry state
  is saved in the database, so it survives a restart.
- **Stop and check.** When a result is unknown, the system stops, then verifies the reservation
  against the original order before continuing. It never assumes.
- **Approved recovery.** A person requests a fix, a *different* admin approves it, then it runs once.
  Every step is recorded.
- **Reliable delivery.** An order is saved together with its "process me" message, so a Redis
  outage cannot lose it.
- **AI investigator (Gemini).** One click gives the root cause, the evidence it used, and a
  recommended action. It can only read; fixed rules check its answer afterwards.
- **Releasing stuck stock.** An approved "release stock" fix gives the inventory back.
- **Measuring the AI.** A fixed set of 10 scenarios, thumbs up/down, and a page showing how often
  its advice was followed and actually worked.
- **A web UI** (React) and a simulated inventory system with five on-purpose failure types.

Screenshots and run instructions: `demo-walkthrough.md`.

## 3. What I unlearned
These are beliefs the project disproved, each from something that really happened:

| I assumed | What turned out to be true |
|---|---|
| "If it timed out, retry." | A timeout can mean the work **succeeded**. Retrying can duplicate it. |
| "Raise an error inside the transaction to simulate a lost reply." | The transaction rolls back, which simulates a *failed* call, not a lost reply. The fake provider needed its **own transaction** that commits first. |
| "Count an attempt when it fails." | If the step fails, its transaction rolls the counter back and retries never end. **Claim the attempt first**, in its own committed step. |
| "The API is healthy, so the system is healthy." | The API was fine while the worker could not reach Redis (a port clash with Redis already on my machine). |
| "A confident AI answer is a good answer." | Confidence is what the model says about itself. I measure advice by what people did with it and whether it worked. |
| "One rule 'never retry if a reservation exists' is safe." | Too broad: retrying the **invoice** step with stock already reserved is perfectly safe. The rule had to depend on the step. |
| "My free API key just works." | Free quota is counted **per model**. One model ran out while others were fine; switching model fixed it. |

## 4. How I used AI
- **Claude Code** (an AI coding assistant) worked inside the repository. I supplied the plans and
  the limits ("schema only", "leave the tests alone"); it wrote most of the code, ran it, and fixed it.
- **Gemini** is part of the product: it investigates failures. It is a helper, not a dependency.
- **I did not trust code I had not seen run.** Each feature was exercised against the real running
  system and its output checked. The AI also had to say what it had **not** verified.
- **I kept the AI's power small on purpose**: read-only tools, a fixed safety layer, and human approval.
- The day-by-day log is in `ai_usage_log.md`.

## 5. What failed
Real mistakes, caught by running things:

- **The worker could not reach Redis** (a port clash). Found only by looking at logs, not at health checks.
- **A helper script emptied two files** (`docker-compose.yml`, `celery_app.py`) before reading them. Restored from git.
- **A retry design flaw**: the attempt counter rolled back with the failed step (see section 3).
- **A slicing mistake** produced a syntax error that crash-looped the containers.
- **Two list endpoints returned HTTP 500** as soon as they had data, because of a coding slip. Found by
  calling them with real rows, not empty ones.
- **My first evaluation script printed PASS when 8 of 10 scenarios had errored.** It now fails when it
  cannot evaluate everything.
- **The AI service itself failed**: a 504 timeout, then free-tier quota exhaustion on one model.
- **A screen showed a form that should have been hidden** on a finished order. Seen in a screenshot.

## What is not finished
- **No automated test suite.** Everything was verified by running it by hand and with scripts.
- **The AI evaluation is small**: one run of 10 scenarios (10/10 correct after the safety rules,
  about 90% before). Results vary between runs.
- **The inventory system is simulated.** A real one would need real idempotency keys.
- **No login rate limiting**, and customer data is not yet redacted before it goes to the model.
