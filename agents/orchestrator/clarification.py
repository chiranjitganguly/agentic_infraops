"""T046 — Orchestrator clarification question builder.

build_clarification_question(top_intents) → str

Formats the top-2 intent candidates into a user-facing question when the
classifier's confidence is below 0.7. Called only on the web channel —
the email channel rejects low-confidence requests without clarification.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IntentCandidate:
    intent: str
    confidence: float
    description: str | None = None


_INTENT_DESCRIPTIONS: dict[str, str] = {
    "provision": "create a new GCP resource (VM, storage bucket, or VPC network)",
    "enquiry": "check the status of an existing GCP resource",
    "faq": "get best-practice guidance or answer a question about GCP",
}


def build_clarification_question(top_intents: list[IntentCandidate]) -> str:
    """Format the top-2 intent candidates into a user-facing clarification question.

    Called when classifier confidence < 0.7 on the web channel.
    Always takes the top 2 candidates by confidence, even if more are provided.

    Args:
        top_intents: Intent candidates sorted by confidence (highest first).

    Returns:
        A human-readable question asking the user to clarify their intent.
    """
    candidates = sorted(top_intents, key=lambda c: c.confidence, reverse=True)[:2]

    if not candidates:
        return (
            "I couldn't understand your request. Could you please rephrase it? "
            "Examples: 'Create a VM with 4 CPUs in us-central1' or "
            "'What is the status of vm-123?'"
        )

    if len(candidates) == 1:
        intent = candidates[0].intent
        desc = candidates[0].description or _INTENT_DESCRIPTIONS.get(intent, intent)
        return (
            f"I think you want to {desc}, but I'm not entirely sure. "
            f"Could you provide more details about your request?"
        )

    lines = ["I'm not sure what you'd like to do. Did you mean:"]
    for i, candidate in enumerate(candidates, start=1):
        desc = candidate.description or _INTENT_DESCRIPTIONS.get(candidate.intent, candidate.intent)
        lines.append(f"  {i}. {desc.capitalize()}")

    lines.append(
        "\nPlease clarify, or rephrase your request with more detail. "
        "Example: 'Create a VM with 4 CPUs in us-central1' or "
        "'What is the status of vm-my-instance?'"
    )

    return "\n".join(lines)
