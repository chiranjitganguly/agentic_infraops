"""T079 — FAQ answer generator skill.

generate_answer(question, chunks) → FAQAnswerResult

Calls LiteLLM gateway to synthesise a cited answer from retrieved chunks.
Returns a fallback message if the LLM call fails or chunks are empty.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import litellm

from contracts.schemas.faq_query import RetrievedChunk
from contracts.shared.logging import get_logger

logger = get_logger("answer-generator")

_SYSTEM_PROMPT = """\
You are an InfraOps platform assistant. Answer the user's question using ONLY the provided context.

Rules:
- If the context does not contain enough information to answer the question, say so clearly.
- Do not fabricate facts that are not present in the context.
- Cite the source document(s) you used (by source_doc name).
- Keep your answer concise: 2-5 sentences.
"""

_FALLBACK_ANSWER = (
    "I was unable to generate an answer at this time. "
    "Please try again or contact the platform engineering team."
)


@dataclass
class FAQAnswerResult:
    answer: str
    sources_cited: list[str] = field(default_factory=list)
    confidence: float = 0.0


def generate_answer(question: str, chunks: list[RetrievedChunk]) -> FAQAnswerResult:
    """Generate a cited answer from retrieved document chunks.

    Uses LiteLLM gateway (synchronous call) to produce a grounded answer.
    Returns a fallback string on LLM errors rather than propagating exceptions.

    Args:
        question: The user's original question.
        chunks: Retrieved document chunks from the knowledge base.

    Returns:
        FAQAnswerResult with answer text, cited sources, and confidence.
    """
    if not chunks:
        return FAQAnswerResult(answer=_FALLBACK_ANSWER, sources_cited=[], confidence=0.0)

    gateway_url = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")
    model = os.environ.get("FAQ_GENERATION_MODEL", "gpt-4o-mini")

    context_parts = [
        f"[Source: {c.source_doc}]\n{c.chunk_text}"
        for c in chunks
    ]
    context = "\n\n---\n\n".join(context_parts)

    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        response = litellm.completion(
            model=model,
            api_base=gateway_url,
            api_key=master_key,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=512,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("answer_generation_failed", question=question[:80], error=str(exc))
        return FAQAnswerResult(answer=_FALLBACK_ANSWER, sources_cited=[], confidence=0.0)

    sources_cited = list({c.source_doc for c in chunks if c.source_doc})
    confidence = max((c.final_score for c in chunks), default=0.0)

    logger.info("answer_generated", question=question[:80], sources=len(sources_cited))
    return FAQAnswerResult(answer=answer, sources_cited=sources_cited, confidence=confidence)
