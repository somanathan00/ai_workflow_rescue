# AI usage log (5 days: 14–18 October 2026)

**Tool:** Claude Code (Anthropic), working in this repository. **Product component:** Gemini (Google),
used by the app itself to investigate failures.

**How the dates were fixed:** from git history and file timestamps, not memory. I did not track hours,
so none are claimed.

| Day | Date | What happened | AI-assisted? |
|---|---|---|---|
| 1 | Tue 14 Oct | Project scaffold committed ("first commit") | Before this log's AI sessions; how it was produced is not recorded |
| 2 | Wed 15 Oct | Made Docker Compose and the Makefile work | Yes |
| 3 | Thu 16 Oct | Redesigned the database schema (added `username`, constraints, indexes) | Yes |
| 4 | Fri 17 Oct | **No work recorded** (no commits, no changed files) | No |
| 5 | Sat 18 Oct | Built everything else: retries, recovery, outbox, AI investigator, UI, evaluation, stock release | Yes |

**Plan vs. reality.** The scaffold's plan was one phase per day, ending with tests on day 5. In practice
the work was bunched into days 2, 3 and 5, and **the automated tests were never written** (I chose to
leave them out). Everything was checked by running it instead.

---

## Day 1 · 14 Oct: Scaffold
- **What:** FastAPI app skeleton, database models and a first migration, Dockerfile, empty placeholder
  files, and a README listing "Day 1 to Day 5" milestones.
- **AI:** not recorded here.

## Day 2 · 15 Oct: Make Compose and the Makefile work
- **I asked:** "the docker compose and make file don't work properly, make it work properly."
- **AI did:** started the stack, read the logs, found the real cause, fixed it.
- **Found:** the worker could not reach Redis. My machine already ran Redis on port 6379, so the
  container never joined the network, while the API still looked healthy. Also `make test` ran
  nothing (the tests were not in the image, and are empty files) and `.env.example` used the wrong names.
- **Changed:** Redis moved to host port 6380; added a `test` service; fixed `.env.example`.
- **I checked:** all services healthy, worker connected to Redis, `/health/live` OK.

## Day 3 · 16 Oct: Better database schema
- **I asked:** add a `username` to users and make all tables production-grade, **with no new tables,
  no new files, and no code in files that were already empty.**
- **AI did:** rewrote the models (value checks, foreign-key rules, indexes, defaults), regenerated the
  first migration, and added username to sign-up and login (email or username).
- **I checked:** sign-up and login by both, duplicate and bad usernames, a bad role rejected by the database.
- **Went wrong / trade-off:** a bad import crashed the first attempt. The first migration was edited in
  place, which is only safe because no real data existed yet.

## Day 4 · 17 Oct: Nothing recorded

## Day 5 · 18 Oct: Everything else
Ten pieces of work, in order. For each, I supplied the plan or the request; the AI wrote and ran it.

1. **Automatic retries.** *Asked:* a plan (retry with 2 s / 4 s waits, a "retry scheduled" state, a
   recoverable test product). *Checked:* four test products ended as expected. *Went wrong:* a helper
   script emptied two files (restored from git); a design flaw would have made retries never end (the
   counter rolled back with the failed step).
2. **Lost-response recovery.** *Asked:* a plan (separate transaction for the fake provider, operation
   keys, reconciliation). *Checked:* lost reply, then reconcile, gave exactly one reservation and one
   invoice; also a crash case. *Went wrong:* a slicing mistake caused a syntax error that crash-looped
   the containers.
3. **Recovery approvals and reliable delivery (outbox).** *Asked:* a plan. *Checked:* orders accepted
   while Redis was stopped and delivered after; every rejection case; one retry that does not reset the budget.
4. **AI investigator (Gemini + LangGraph).** *Asked:* a plan. *Checked:* with scripted model answers
   (no key yet): unsafe retry downgraded, made-up evidence rejected, no model call for finished orders.
5. **Cleanup and docs.** Pinned dependencies, lint, CI file, JSON logs, health and metrics endpoints,
   seed and demo scripts, README, architecture notes. *Checked:* `make scenarios` and `make demo`.
6. **Frontend and folder split.** *Asked:* "a valid frontend, two folders, Compose runs both."
   *Checked:* drove the UI in a headless browser (sign in, order, request, approve, execute, mobile).
   *Went wrong:* the first list endpoints returned 500 as soon as they had data.
7. **Suggestions only.** *Asked:* ideas to make the AI more useful, "don't implement anything." I then
   chose two: AI evaluation and stock release.
8. **Evaluation and stock release.** Built both; checked the full release flow, 200 bad AI answers
   through the safety rules (none unsafe got through), migrations from zero. *Went wrong:* a duplicate
   argument made one endpoint return 500; my first evaluation script printed PASS when 8 of 10
   scenarios had errored.
9. **Gemini key trouble.** *Asked:* "the Gemini key gives a lot of issues." *Found:* the key was fine;
   one model's free quota was used up (quota is per model). Compared two other models on the 10
   scenarios and switched the default to `gemini-flash-lite-latest`. *Checked:* all four failure types
   got the right recommendation through the real app.
10. **Submission documents.** Wrote these quest files and captured screenshots of the running app.
    The screenshots exposed one more UI flaw (a form shown on a finished order), which was fixed.

---

## How I decided what to trust
- **Nothing counted as done until it ran** against the real containers, database and queue.
- **The AI had to list what it had not verified.** For example, the real-model results were marked
  "pending" until the quota allowed a real run.
- **I limited the AI's reach** in the product itself: it can only read, and fixed rules plus a human
  approval stand between its advice and any change.

## Totals
| | |
|---|---|
| Days with recorded work | 4 of 5 (14, 15, 16, 18 Oct) |
| Problems found by running things | 8 (see `writeup.md`, "What failed") |
| Automated tests written | 0 |
| Real-model evaluation | 10 scenarios, one run: 10/10 correct after the safety rules, about 90% before |
