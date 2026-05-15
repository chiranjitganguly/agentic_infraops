"""T093 — Clarification trigger evaluation.

Verifies:
  - Ambiguous inputs (confidence < 0.7) correctly trigger clarification
  - High-confidence inputs do NOT incorrectly trigger clarification

Uses a curated subset of the intent_classification.jsonl dataset
plus dedicated ambiguous examples.

Usage:
    python -m evaluations.intent_classification.evaluate_clarification [--verbose]
"""
from __future__ import annotations

import argparse
import asyncio
import sys

_CLARIFICATION_THRESHOLD = 0.7

# Inputs that SHOULD trigger clarification (confidence < 0.7)
_AMBIGUOUS_INPUTS = [
    "do the thing",
    "make it faster",
    "...",
    "setup",
    "help",
    "something with storage",
    "I need a thing in GCP",
    "can you help with infra",
    "Please advise on the best approach",
    "fix the problem",
]

# Inputs that should NOT trigger clarification (confidence >= 0.7)
_CLEAR_INPUTS = [
    "Create a VM with 4 CPUs in us-central1",
    "What is the status of vm-web-01?",
    "What is the best practice for VPC subnet design in GCP?",
    "Provision a new bucket called my-data-bucket in us-east1",
    "List all VMs in us-central1",
    "How do I configure IAM roles to follow least privilege?",
    "Create an e2-standard-8 VM named web-server-01 in us-central1-a",
    "Check if bucket my-data-bucket exists",
    "What is Cloud NAT and when should I use it?",
    "Set up a VPC network named prod-network in europe-west1",
]


async def _run_check(input_text: str, should_clarify: bool, verbose: bool) -> dict:
    from skills.intent_classification.classifier import classify

    try:
        result = await classify(input_text, channel="web")
        confidence = result.confidence
        triggers_clarification = confidence < _CLARIFICATION_THRESHOLD
    except Exception as exc:
        if verbose:
            print(f"  [ERROR] '{input_text[:60]}': {exc}")
        return {"input": input_text, "should_clarify": should_clarify, "correct": False, "confidence": 0.0}

    correct = triggers_clarification == should_clarify

    if verbose:
        status = "PASS" if correct else "FAIL"
        expected_str = "clarify" if should_clarify else "no-clarify"
        actual_str = "clarify" if triggers_clarification else "no-clarify"
        print(f"  [{status}] conf={confidence:.2f} expected={expected_str} got={actual_str} | '{input_text[:60]}'")

    return {"input": input_text, "should_clarify": should_clarify, "correct": correct, "confidence": confidence}


async def run_evaluation(verbose: bool) -> int:
    print("Evaluating clarification trigger behaviour...")
    if verbose:
        print()

    tasks = (
        [(_run_check(t, True, verbose)) for t in _AMBIGUOUS_INPUTS]
        + [(_run_check(t, False, verbose)) for t in _CLEAR_INPUTS]
    )
    results = await asyncio.gather(*tasks)

    ambiguous_results = [r for r in results if r["should_clarify"]]
    clear_results = [r for r in results if not r["should_clarify"]]

    def _rate(rs: list[dict]) -> tuple[int, int, float]:
        correct = sum(1 for r in rs if r["correct"])
        total = len(rs)
        return correct, total, correct / total if total else 0.0

    amb_c, amb_t, amb_rate = _rate(ambiguous_results)
    clr_c, clr_t, clr_rate = _rate(clear_results)
    all_c, all_t, all_rate = _rate(list(results))

    print()
    print("─" * 55)
    print(f"{'Category':<25} {'Correct':>8} {'Total':>6} {'Rate':>10}")
    print("─" * 55)
    print(f"{'Ambiguous (should clarify)':<25} {amb_c:>8} {amb_t:>6} {amb_rate:>9.1%}")
    print(f"{'Clear (no clarify)':<25} {clr_c:>8} {clr_t:>6} {clr_rate:>9.1%}")
    print("─" * 55)
    print(f"{'OVERALL':<25} {all_c:>8} {all_t:>6} {all_rate:>9.1%}")
    print("─" * 55)

    threshold = 0.80
    print()
    if all_rate < threshold:
        print(f"FAIL: clarification accuracy {all_rate:.1%} < required {threshold:.0%}")
        return 1

    print(f"PASS: clarification accuracy {all_rate:.1%} >= required {threshold:.0%}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Clarification trigger evaluation")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    exit_code = asyncio.run(run_evaluation(args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
