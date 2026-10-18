"""Evaluate the AI investigator against known failure scenarios.

    python scripts/evaluate_investigator.py --offline     # guardrails only, no API key
    python scripts/evaluate_investigator.py               # asks the real model (needs GEMINI_API_KEY)
    python scripts/evaluate_investigator.py --repeat 3 --json report.json

Exit status is 1 if any UNSAFE recommendation survives the guardrails, so it
can gate a prompt or model change. Keep the live run out of normal CI: it
needs a key, costs tokens and is not perfectly repeatable.
"""

import argparse
import json
import sys
from collections import Counter

from app.agents.evaluation import CASES, run_live, run_offline, summarize


def print_cases() -> None:
    print("Scenarios:")
    for case in CASES:
        print(f"  {case.id:<28} acceptable={sorted(case.acceptable)} unsafe={sorted(case.unsafe)}")
    print()


def print_live(rows) -> None:
    print(f"{'case':<28}{'model said':<24}{'final':<24}{'conf':<6}{'verdict'}")
    for r in rows:
        if r.verdict == "error":
            print(f"{r.case:<28}ERROR  {r.violations[0] if r.violations else ''}")
            continue
        mark = "" if not r.downgraded else "  (guardrails changed it)"
        print(f"{r.case:<28}{r.model_action:<24}{r.final_action:<24}{r.confidence:<6.2f}{r.verdict}{mark}")


def print_offline(rows) -> None:
    by_case = Counter()
    leaks = [r for r in rows if r.verdict == "UNSAFE"]
    for r in rows:
        by_case[r.case] += 1
    print(f"{'case':<28}{'adversarial answers':<22}{'unsafe that got through'}")
    for case in CASES:
        bad = sum(1 for r in leaks if r.case == case.id)
        print(f"{case.id:<28}{by_case[case.id]:<22}{bad}")
    for r in leaks[:10]:
        print(f"  LEAK {r.case}: {r.source} -> {r.final_action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="adversarial test of the guardrails; no model call")
    parser.add_argument("--repeat", type=int, default=1, help="live runs per scenario")
    parser.add_argument("--case", action="append", help="limit to a scenario id (repeatable)")
    parser.add_argument("--json", help="write the full report to this file")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="fail if live accuracy is lower")
    args = parser.parse_args()

    print_cases()

    if args.offline:
        rows = run_offline()
        print_offline(rows)
    else:
        from app.agents.investigator import _default_analyzer
        from app.infrastructure.llm.client import LLMUnavailable

        try:
            analyzer = _default_analyzer()
        except LLMUnavailable as exc:
            print(f"Cannot run the live evaluation: {exc}. Use --offline, or set GEMINI_API_KEY.")
            return 2

        rows = run_live(analyzer, args.repeat, set(args.case) if args.case else None)
        print_live(rows)

    summary = summarize(rows)
    print("\nSummary")
    for key, value in summary.items():
        print(f"  {key:<32}{value}")

    if args.json:
        with open(args.json, "w") as handle:
            json.dump({"summary": summary, "rows": [r.__dict__ for r in rows]}, handle, indent=2)
        print(f"\nReport written to {args.json}")

    if summary["unsafe_after_guardrails"]:
        print("\nFAIL: an unsafe recommendation survived the guardrails.")
        return 1

    if summary["errors"]:
        print(
            f"\nINCOMPLETE: {summary['errors']} scenario(s) could not be evaluated "
            "(see ERROR lines above), so this result proves nothing about them."
        )
        return 2

    if not args.offline and (summary["final_accuracy"] or 0) < args.min_accuracy:
        print(f"\nFAIL: accuracy {summary['final_accuracy']} is below {args.min_accuracy}.")
        return 1

    print("\nPASS: no unsafe recommendation got through.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
