"""T078 — Document retrieval skill.

retrieve(question, top_k, kb_client) → list[RetrievedChunk]

Calls knowledge-base-mcp search_documents with hybrid BM25 + vector search.
Returns empty list if no chunks meet the score threshold.
Injectable kb_client for testing.
"""
from __future__ import annotations

from typing import Protocol

from contracts.schemas.faq_query import RetrievedChunk
from contracts.shared.logging import get_logger

logger = get_logger("document-retrieval")

_SCORE_THRESHOLD = 0.5


class KnowledgeBaseClient(Protocol):
    def search_documents(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
    ) -> list[dict]: ...


def _default_kb_client() -> KnowledgeBaseClient:
    from mcp_servers.knowledge_base import server
    return server  # type: ignore[return-value]


def retrieve(
    question: str,
    top_k: int = 5,
    kb_client: KnowledgeBaseClient | None = None,
) -> list[RetrievedChunk]:
    """Retrieve relevant document chunks for a question.

    Calls the knowledge-base MCP server's hybrid search. Chunks below the
    score threshold are excluded by the MCP server itself.

    Args:
        question: Natural language question.
        top_k: Maximum number of chunks to return.
        kb_client: Injectable knowledge base client (defaults to mcp_servers.knowledge_base).

    Returns:
        List of RetrievedChunk objects sorted by final_score descending.
        Empty list if no relevant chunks found.
    """
    client = kb_client if kb_client is not None else _default_kb_client()

    try:
        raw_results = client.search_documents(
            query=question,
            top_k=top_k,
            score_threshold=_SCORE_THRESHOLD,
        )
    except Exception as exc:
        logger.warning("retrieve_failed", question=question[:80], error=str(exc))
        return []

    chunks = [
        RetrievedChunk(
            chunk_text=r.get("chunk_text", ""),
            source_doc=r.get("source_doc", ""),
            bm25_score=float(r.get("bm25_score", 0.0)),
            vector_score=float(r.get("vector_score", 0.0)),
            final_score=float(r.get("final_score", 0.0)),
            chunk_id=r.get("chunk_id"),
        )
        for r in raw_results
        if r.get("chunk_text")
    ]

    logger.info("retrieve_done", question=question[:80], chunks=len(chunks))
    return chunks
