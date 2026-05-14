"""FAQ Agent: Google ADK implementation.

Handles natural-language questions about GCP infrastructure by searching the
knowledge base (Qdrant via knowledge-base-mcp) and generating answers via LiteLLM.

Input:  JSON-serialised FAQInput
Output: JSON-serialised FAQAnsweredOutput | FAQNoResultsOutput
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from contracts.agents.faq import FAQAnsweredOutput, FAQInput, FAQNoResultsOutput, Source
from contracts.shared.logging import configure_logging, get_logger
from contracts.shared.metrics import start_metrics_server

configure_logging(service_name="faq-agent")
logger = get_logger("faq-agent")

_LITELLM_GATEWAY_URL = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
_LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
_FAQ_MODEL = os.environ.get("FAQ_GENERATION_MODEL", "gpt-4o-mini")
_KNOWLEDGE_BASE_URL = os.environ.get("KNOWLEDGE_BASE_MCP_URL", "http://mcp-knowledge-base:8093")

_ANSWER_PROMPT = """\
You are an InfraOps platform assistant. Answer the user's question using ONLY the context below.
If the context is insufficient, say so clearly.

Context:
{context}

Question: {question}

Answer concisely in 2-5 sentences. Do not hallucinate facts not present in the context.
"""


def _search_documents(question: str, top_k: int) -> list[dict]:
    """Call knowledge-base MCP SSE server via its REST tool endpoint."""
    try:
        resp = httpx.post(
            f"{_KNOWLEDGE_BASE_URL}/tools/search_documents",
            json={"query": question, "top_k": top_k, "score_threshold": 0.3},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json() or []
    except Exception as exc:
        logger.warning("knowledge_base_search_failed", error=str(exc))
        # Fall back to direct import when running in the same process (tests/dev)
        try:
            from mcp_servers.knowledge_base.server import search_documents
            return search_documents(query=question, top_k=top_k, score_threshold=0.3)
        except Exception:
            return []


def _generate_answer(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[{i+1}] {c['chunk_text']}" for i, c in enumerate(chunks)
    )
    prompt = _ANSWER_PROMPT.format(context=context, question=question)

    try:
        resp = httpx.post(
            f"{_LITELLM_GATEWAY_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {_LITELLM_MASTER_KEY}"},
            json={
                "model": _FAQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("answer_generation_failed", error=str(exc))
        return "I was unable to generate an answer at this time. Please try again."


async def handle_faq(inp: FAQInput) -> dict:
    """Core FAQ logic — injectable for testing."""
    now = datetime.now(timezone.utc)

    chunks = _search_documents(inp.question, inp.max_chunks)

    if not chunks:
        logger.info("faq_no_results", question=inp.question[:80])
        return FAQNoResultsOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            answered_at=now,
        ).model_dump(mode="json")

    answer = _generate_answer(inp.question, chunks)

    sources = [
        Source(
            document_title=c.get("source_doc", "Unknown"),
            document_url=c.get("source_doc"),
            chunk_excerpt=c.get("chunk_text", "")[:200],
            relevance_score=min(1.0, max(0.0, c.get("final_score", 0.5))),
        )
        for c in chunks
    ]

    logger.info("faq_answered", question=inp.question[:80], sources=len(sources))
    return FAQAnsweredOutput(
        correlation_id=inp.correlation_id,
        request_id=inp.request_id,
        answer=answer,
        sources=sources,
        confidence=max((s.relevance_score for s in sources), default=None),
        answered_at=now,
    ).model_dump(mode="json")


class FAQAgent(BaseAgent):
    """ADK BaseAgent for FAQ retrieval and answer generation."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_text = ""
        if ctx.user_content and ctx.user_content.parts:
            user_text = ctx.user_content.parts[0].text or ""

        try:
            task_data = json.loads(user_text)
            if "message" in task_data:
                parts = task_data["message"].get("parts", [])
                task_data = parts[0].get("data", {}) if parts else {}
            inp = FAQInput(**task_data)
        except Exception as exc:
            error_out = {"error": f"Invalid FAQ input: {exc}"}
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=json.dumps(error_out))],
                ),
            )
            return

        logger.info("faq_started", question=inp.question[:80], user=inp.requesting_user)

        try:
            output = await handle_faq(inp)
        except Exception as exc:
            logger.error("faq_failed", error=str(exc))
            output = {
                "correlation_id": str(inp.correlation_id),
                "request_id": str(inp.request_id),
                "status": "error",
                "message": f"FAQ lookup failed: {exc}",
            }

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=json.dumps(output))],
            ),
        )


root_agent = FAQAgent(
    name="faq_agent",
    description="Answers GCP infrastructure questions by searching the knowledge base.",
)


if __name__ == "__main__":
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", "8004"))
    start_metrics_server(port=9004)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        web=False,
        a2a=True,
        host="0.0.0.0",
        port=port,
        allow_origins=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
