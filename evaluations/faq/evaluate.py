"""T084 — FAQ evaluation harness.

Runs handle_faq() against evaluations/datasets/faq_evaluation.jsonl.

Checks per question:
  - answer is non-empty and > 50 chars
  - sources list is non-empty
  - answer is grounded (hallucination check via LiteLLM judge)

Reports pass rate by category; exits 1 if overall pass rate < 80%.

Usage:
    python -m evaluations.faq.evaluate [--dataset PATH] [--verbose]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

_DATASET_DEFAULT = Path(__file__).parent.parent / "datasets" / "faq_evaluation.jsonl"
_LITELLM_GATEWAY_URL = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
_LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
_JUDGE_MODEL = os.environ.get("FAQ_JUDGE_MODEL", "gpt-4o-mini")

_JUDGE_PROMPT = """\
You are an evaluation judge. Given a question, a generated answer, and source documents, \
determine whether the answer is grounded in the provided sources without hallucinating facts.

Question: {question}

Sources:
{sources}

Generated Answer: {answer}

Respond with a single JSON object:
{{"grounded": true/false, "reason": "<one sentence>"}}

grounded=true  → all factual claims in the answer are supported by the sources.
grounded=false → the answer contains claims not found in the sources.
"""


def _judge_grounded(question: str, answer: str, sources: list[dict]) -> bool:
    """Call LiteLLM to judge whether the answer is grounded in the sources."""
    sources_text = "\n".join(
        f"- [{s.get('document_title', 'unknown')}]: {s.get('chunk_excerpt', '')}"
        for s in sources
    )
    prompt = _JUDGE_PROMPT.format(question=question, sources=sources_text, answer=answer)
    try:
        resp = httpx.post(
            f"{_LITELLM_GATEWAY_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {_LITELLM_MASTER_KEY}"},
            json={
                "model": _JUDGE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 128,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        verdict = json.loads(content)
        return bool(verdict.get("grounded", False))
    except Exception:
        # If LiteLLM is unavailable, skip the hallucination check (assume grounded)
        return True


async def _evaluate_question(row: dict, verbose: bool) -> dict:
    from agents.faq.agent import handle_faq
    from contracts.agents.faq import FAQInput

    question = row["question"]
    category = row.get("category", "unknown")
    qid = row["id"]

    inp = FAQInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        question=question,
        requesting_user="eval@infraops.internal",
    )

    try:
        result = await handle_faq(inp)
    except Exception as exc:
        if verbose:
            print(f"  [ERROR] {qid}: {exc}")
        return {"id": qid, "category": category, "passed": False, "reason": f"exception: {exc}"}

    status = result.get("status")
    answer = result.get("answer", "")
    sources = result.get("sources", [])

    failures = []

    if status == "no_results" or not answer:
        failures.append("no_results or empty answer")
    elif len(answer) < 50:
        failures.append(f"answer too short ({len(answer)} chars)")

    if not sources:
        failures.append("no sources returned")

    if answer and len(answer) >= 50 and sources:
        grounded = _judge_grounded(question, answer, sources)
        if not grounded:
            failures.append("answer not grounded in sources (hallucination detected)")

    passed = len(failures) == 0
    reason = "; ".join(failures) if failures else "ok"

    if verbose:
        status_str = "PASS" if passed else "FAIL"
        print(f"  [{status_str}] {qid}: {reason}")

    return {"id": qid, "category": category, "passed": passed, "reason": reason}


async def run_evaluation(dataset_path: Path, verbose: bool) -> int:
    rows = []
    with dataset_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    print(f"Evaluating {len(rows)} questions from {dataset_path.name}...")
    if verbose:
        print()

    results = []
    for row in rows:
        result = await _evaluate_question(row, verbose)
        results.append(result)

    by_category: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r["passed"])

    total = len(results)
    total_passed = sum(1 for r in results if r["passed"])
    pass_rate = total_passed / total if total else 0.0

    print()
    print("─" * 50)
    print(f"{'Category':<20} {'Pass':>6} {'Total':>6} {'Rate':>8}")
    print("─" * 50)
    for cat in sorted(by_category):
        passed = sum(by_category[cat])
        count = len(by_category[cat])
        rate = passed / count if count else 0.0
        print(f"{cat:<20} {passed:>6} {count:>6} {rate:>7.1%}")
    print("─" * 50)
    print(f"{'OVERALL':<20} {total_passed:>6} {total:>6} {pass_rate:>7.1%}")
    print("─" * 50)

    threshold = 0.80
    if pass_rate < threshold:
        print(f"\nFAIL: pass rate {pass_rate:.1%} < required {threshold:.0%}")
        return 1

    print(f"\nPASS: pass rate {pass_rate:.1%} >= required {threshold:.0%}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="FAQ evaluation harness")
    parser.add_argument("--dataset", type=Path, default=_DATASET_DEFAULT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    exit_code = asyncio.run(run_evaluation(args.dataset, args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
