"""T092 — Intent classification evaluation harness.

Runs the intent_classification skill against evaluations/datasets/intent_classification.jsonl.

Reports:
  - accuracy per intent class
  - overall accuracy
  - confusion matrix

Exits 1 if overall accuracy < 90% (SC-002).

Usage:
    python -m evaluations.intent_classification.evaluate [--dataset PATH] [--verbose]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

_DATASET_DEFAULT = (
    Path(__file__).parent.parent / "datasets" / "intent_classification.jsonl"
)
_ACCURACY_THRESHOLD = 0.90
_INTENTS = ["provision", "enquiry", "faq"]


async def _classify_one(row: dict, verbose: bool) -> dict:
    from skills.intent_classification.classifier import classify

    input_text = row["input"]
    expected = row["expected_intent"]
    qid = row["id"]
    notes = row.get("notes", "")

    try:
        result = await classify(input_text, channel="web")
        predicted = result.intent
        confidence = result.confidence
    except Exception as exc:
        if verbose:
            print(f"  [ERROR] {qid}: {exc}")
        return {"id": qid, "expected": expected, "predicted": "error", "correct": False, "confidence": 0.0, "notes": notes}

    correct = predicted == expected
    if verbose:
        status = "PASS" if correct else "FAIL"
        print(f"  [{status}] {qid} | expected={expected:10} predicted={predicted:10} conf={confidence:.2f} | {notes}")

    return {"id": qid, "expected": expected, "predicted": predicted, "correct": correct, "confidence": confidence, "notes": notes}


async def run_evaluation(dataset_path: Path, verbose: bool) -> int:
    rows = []
    with dataset_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    print(f"Evaluating {len(rows)} examples from {dataset_path.name}...")
    if verbose:
        print()

    results = []
    for row in rows:
        r = await _classify_one(row, verbose)
        results.append(r)

    # Per-class accuracy
    per_class_correct: dict[str, int] = defaultdict(int)
    per_class_total: dict[str, int] = defaultdict(int)
    for r in results:
        per_class_total[r["expected"]] += 1
        if r["correct"]:
            per_class_correct[r["expected"]] += 1

    # Confusion matrix: confusion[actual][predicted] = count
    confusion: dict[str, dict[str, int]] = {i: defaultdict(int) for i in _INTENTS}
    for r in results:
        actual = r["expected"]
        predicted = r["predicted"] if r["predicted"] in _INTENTS else "other"
        if actual in _INTENTS:
            confusion[actual][predicted] += 1

    total = len(results)
    total_correct = sum(1 for r in results if r["correct"])
    overall = total_correct / total if total else 0.0

    print()
    print("─" * 50)
    print(f"{'Intent':<15} {'Correct':>8} {'Total':>6} {'Accuracy':>10}")
    print("─" * 50)
    for intent in _INTENTS:
        c = per_class_correct[intent]
        t = per_class_total[intent]
        acc = c / t if t else 0.0
        print(f"{intent:<15} {c:>8} {t:>6} {acc:>9.1%}")
    print("─" * 50)
    print(f"{'OVERALL':<15} {total_correct:>8} {total:>6} {overall:>9.1%}")
    print("─" * 50)

    # Confusion matrix
    print()
    print("Confusion matrix (rows=actual, cols=predicted):")
    header_cols = _INTENTS + ["other"]
    col_w = 12
    print(f"{'actual \\ pred':<15}" + "".join(f"{c:>{col_w}}" for c in header_cols))
    print("─" * (15 + col_w * len(header_cols)))
    for actual in _INTENTS:
        row_str = f"{actual:<15}"
        for pred in header_cols:
            row_str += f"{confusion[actual][pred]:>{col_w}}"
        print(row_str)

    print()
    if overall < _ACCURACY_THRESHOLD:
        print(f"FAIL: accuracy {overall:.1%} < required {_ACCURACY_THRESHOLD:.0%} (SC-002)")
        return 1

    print(f"PASS: accuracy {overall:.1%} >= required {_ACCURACY_THRESHOLD:.0%} (SC-002)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent classification evaluation")
    parser.add_argument("--dataset", type=Path, default=_DATASET_DEFAULT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    exit_code = asyncio.run(run_evaluation(args.dataset, args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
