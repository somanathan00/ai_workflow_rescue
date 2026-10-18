# 003: The AI recommends, deterministic code decides

**Status:** accepted

## Context
LLM output can be wrong, can be steered by text in logs, and can sound confident without
evidence. Recovery actions have real side effects.

## Decision
- The investigator is read-only and has no tool that changes state or runs arbitrary SQL.
- It sees only tool-produced evidence with stable references; logs and errors are untrusted.
- Output is schema-validated, then `apply_guardrails` can only make it safer (cited references
  must exist, minimum confidence, no retry over an existing side effect, no reconciliation
  without a matching reservation, recovery policy must allow it).
- A recommendation is applied only through the recovery APIs, which re-validate against live
  state and require admin approval. Gemini being down changes nothing about recovery.

## Consequences
- The original model output and the guardrail verdict are both stored (`policy_result`) so
  disagreement is measurable.
- Confidence is model-reported and is not treated as a calibrated probability.
- Adding a new recommended action means adding it to the recovery policy first.
