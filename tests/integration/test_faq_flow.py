"""T085 — Integration test: end-to-end FAQ flow.

Tests:
  1. FAQ answered — mock search returns chunks, mock generate returns answer
  2. FAQ no results — mock search returns empty list
  3. Audit event emitted for answered case
  4. Audit event emitted for no_results case
  5. Answered response within 60-second SLA

Uses in-process stubs — no external services required.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from agents.faq.agent import handle_faq
from contracts.agents.faq import FAQInput

pytestmark = pytest.mark.integration

# ─── Shared fixtures ─────────────────────────────────────────────────────────

_FAKE_CHUNKS = [
    {
        "chunk_id": "chunk-001",
        "chunk_text": "Use VPC shared networks to centralise networking for your organisation.",
        "source_doc": "gcp-vpc-best-practices.md",
        "bm25_score": 0.3,
        "vector_score": 0.85,
        "final_score": 0.82,
    },
    {
        "chunk_id": "chunk-002",
        "chunk_text": "Enable Private Google Access on subnets to allow VM instances to reach Google APIs.",
        "source_doc": "gcp-vpc-best-practices.md",
        "bm25_score": 0.25,
        "vector_score": 0.78,
        "final_score": 0.76,
    },
]

_FAKE_ANSWER = "Use VPC shared networks and enable Private Google Access for best security."


def _make_input(**overrides) -> FAQInput:
    base = dict(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        question="What is the best practice for VPC design on GCP?",
        requesting_user="dev@example.com",
    )
    base.update(overrides)
    return FAQInput(**base)


# ─── Answered case ────────────────────────────────────────────────────────────

async def test_faq_answered_returns_answer_and_sources() -> None:
    """FAQ with matching chunks returns status=answered with non-empty answer and sources."""
    inp = _make_input()

    with (
        patch("agents.faq.agent._search_documents", return_value=_FAKE_CHUNKS),
        patch("agents.faq.agent._generate_answer", return_value=_FAKE_ANSWER),
        patch("agents.faq.agent.emit_audit_event", new_callable=AsyncMock),
        patch("agents.faq.agent._store_faq_query", new_callable=AsyncMock),
    ):
        result = await handle_faq(inp)

    assert result["status"] == "answered"
    assert result["answer"] == _FAKE_ANSWER
    assert len(result["sources"]) == 2
    assert result["sources"][0]["document_title"] == "gcp-vpc-best-practices.md"
    assert result["answered_at"] is not None


# ─── No results case ─────────────────────────────────────────────────────────

async def test_faq_no_results_when_chunks_empty() -> None:
    """FAQ with no matching chunks returns status=no_results."""
    inp = _make_input(question="What is the capital of Mars?")

    with (
        patch("agents.faq.agent._search_documents", return_value=[]),
        patch("agents.faq.agent.emit_audit_event", new_callable=AsyncMock),
        patch("agents.faq.agent._store_faq_query", new_callable=AsyncMock),
    ):
        result = await handle_faq(inp)

    assert result["status"] == "no_results"
    assert "No relevant documentation" in result["message"]


# ─── Audit events ─────────────────────────────────────────────────────────────

async def test_audit_event_emitted_for_answered() -> None:
    """emit_audit_event is called with faq_answered event type for answered result."""
    inp = _make_input()
    mock_audit = AsyncMock()

    with (
        patch("agents.faq.agent._search_documents", return_value=_FAKE_CHUNKS),
        patch("agents.faq.agent._generate_answer", return_value=_FAKE_ANSWER),
        patch("agents.faq.agent.emit_audit_event", mock_audit),
        patch("agents.faq.agent._store_faq_query", new_callable=AsyncMock),
    ):
        await handle_faq(inp)

    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["payload"]["answered"] is True
    assert call_kwargs["payload"]["source_count"] == 2


async def test_audit_event_emitted_for_no_results() -> None:
    """emit_audit_event is called even when no chunks are found."""
    inp = _make_input()
    mock_audit = AsyncMock()

    with (
        patch("agents.faq.agent._search_documents", return_value=[]),
        patch("agents.faq.agent.emit_audit_event", mock_audit),
        patch("agents.faq.agent._store_faq_query", new_callable=AsyncMock),
    ):
        await handle_faq(inp)

    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["payload"]["answered"] is False
    assert call_kwargs["payload"]["source_count"] == 0


# ─── SLA ─────────────────────────────────────────────────────────────────────

async def test_faq_answered_within_60s_sla() -> None:
    """FAQ response completes within 60-second SLA."""
    inp = _make_input()

    with (
        patch("agents.faq.agent._search_documents", return_value=_FAKE_CHUNKS),
        patch("agents.faq.agent._generate_answer", return_value=_FAKE_ANSWER),
        patch("agents.faq.agent.emit_audit_event", new_callable=AsyncMock),
        patch("agents.faq.agent._store_faq_query", new_callable=AsyncMock),
    ):
        start = time.perf_counter()
        result = await handle_faq(inp)
        elapsed = time.perf_counter() - start

    assert elapsed < 60.0, f"SLA exceeded: {elapsed:.2f}s"
    assert result["status"] == "answered"
