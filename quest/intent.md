# Intent

## The problem I picked
Online orders often involve a second system (here: inventory). Sometimes that system does the work
but the reply never arrives. The order system then has to guess:

- **Retry?** It might reserve the stock twice (or charge twice).
- **Give up?** The order is stuck and nobody knows.
- **Stop and ask a person?** Now someone has to work out what happened from scattered logs.

Real failures are not only "it crashed". The dangerous one is **"I don't know if it worked."**

## What I set out to build
A small order system that handles failure carefully, in this order:

1. **Keep a record** of everything that happens to an order.
2. **Retry on its own, but only when that is provably safe** (a temporary problem, nothing changed yet).
3. **Stop when the result is unknown**, then check what really happened before going on.
4. **Use an AI to explain the failure** and recommend the safest next step.
5. **Let a person approve** anything that changes an order. The AI only advises.
6. **Undo work for orders that can never finish**, so stock is not held for nothing.
7. **Measure the AI**, so we know if it actually helps.

## Who it is for
- **Operators**, who place and watch orders and ask for fixes.
- **Admins**, who approve fixes and check how good the AI is.

## What it is deliberately not
- **Not a fully automatic fixer.** Every fix needs a person's approval.
- **Not a real inventory or billing system.** The outside system is simulated, so failures can be
  reproduced on demand (a product ID decides what goes wrong).
- **Not a large distributed system.** One codebase and one database keep the safety guarantees easy
  to explain and to prove.

## How I will know it worked (success criteria)
| Situation | Expected result |
|---|---|
| Normal order | Completes |
| Fails twice for a temporary reason | Fixes itself, completes on the 3rd try |
| Keeps failing | Stops after 3 tries and is never retried forever |
| Request can never work | Fails at once, no pointless retries |
| Work done but reply lost | Stops, then after approval the order completes with **exactly one** reservation and one invoice |
| Fails after stock was reserved | Stock can be released and the order closed cleanly |
| Redis is down when an order arrives | The order is still accepted and processed later |
| AI suggests something unsafe | The unsafe suggestion is changed to a safe one before anyone sees it |
| AI is unavailable | Everything still works, just without the AI explanation |

## Constraints I set
- Safety rules are written in ordinary code, not left to the AI.
- Every claim is checked by running it, not by reading the code.
- Be honest about what is not finished (see `writeup.md`).
