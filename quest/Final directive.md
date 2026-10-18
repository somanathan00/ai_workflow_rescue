# Final directive

*The rules the finished system follows, and the rules I held the AI collaborator to while building it.
If a future change breaks one of these, the change is wrong.*

## The system must always
1. **Never repeat a side effect it cannot prove is safe to repeat.** If a result is unknown, stop and check first.
2. **Treat "not found" as "unknown", not as "did not happen".**
3. **Record every decision.** Every retry, approval, execution and AI recommendation leaves an event.
4. **Need a person's approval to change an order.** An admin approves; nobody approves their own request.
5. **Re-check the rules at the moment of action**, not only when the request was made.
6. **Keep working without the AI.** If the AI is down or out of quota, recovery still works.
7. **Accept an order even if Redis is down.** An order is saved together with its "please process" message.
8. **Stay safe if run twice.** Every worker task must tolerate duplicate delivery and crashes.
9. **Never keep stock for an order that can never finish**, once a person approves releasing it.
10. **Only use failure-injection (the `SIM-*` products) in development or test.**

## The AI must always
- **Only read.** It has no way to change data, run its own queries, approve, or execute anything.
- **Only use supplied evidence.** Every fact it cites must be a reference the system gave it.
- **Separate facts from guesses.**
- **Be checked by fixed rules afterwards.** Those rules can make its advice safer, never riskier.
- **Be measured.** Its advice is judged by what people did with it and whether it worked, not by its own confidence.

## How I worked with the AI collaborator (Claude Code)
- I decided **what** to build (the plans and the scope); the AI wrote most of the code.
- **Nothing counts as done until it was run.** Each feature was exercised against the real running
  system (containers, database, queue), and its output checked.
- **The AI had to say what it had not verified**, instead of implying it.
- **Scope limits were obeyed**: e.g. "schema only, no new tables" for one task, "leave the tests
  alone" for later ones.
- **Destructive actions needed care**: nothing outside this project's own containers, volumes and
  test accounts was deleted, and test data was removed afterwards.
- **Secrets stay out of the repo**: keys live only in `.env`, which git ignores.

## State at hand-over
- **Works and was checked:** retries, uncertain-outcome recovery, recovery approvals, reliable
  delivery (outbox), AI investigation, stock release (compensation), the web UI, evaluation of the AI.
- **Not finished (stated plainly):** no automated test suite; the AI evaluation is one run of
  10 scenarios; the outside inventory system is simulated; no login rate limiting.
