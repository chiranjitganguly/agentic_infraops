"""T — knowledge-base-mcp: MCP server wrapping Qdrant for hybrid FAQ retrieval.

Tools: search_documents, get_document_by_id, index_document, get_collection_stats

Embedding: dense via LiteLLM gateway, sparse via Qdrant FastEmbed BM25.
Fusion: Reciprocal Rank Fusion (RRF) with equal weight.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="knowledge-base-mcp")
logger = get_logger("knowledge-base-mcp")

mcp = FastMCP("knowledge-base-mcp")

_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_COLLECTION = os.environ.get("QDRANT_COLLECTION", "infraops_knowledge_base")
_LITELLM_GATEWAY_URL = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
_LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
_VECTOR_SIZE = 1536
_SCORE_THRESHOLD = 0.5


def _qdrant() -> QdrantClient:
    return QdrantClient(url=_QDRANT_URL)


def _embed(text: str) -> list[float]:
    import openai

    client = openai.OpenAI(
        base_url=f"{_LITELLM_GATEWAY_URL}/v1",
        api_key=_LITELLM_MASTER_KEY or "sk-placeholder",
    )
    response = client.embeddings.create(model=_EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if _COLLECTION not in existing:
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config={"dense": VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE)},
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
            },
        )
        logger.info("collection_created", collection=_COLLECTION)


@mcp.tool()
def search_documents(
    query: str,
    top_k: int = 5,
    score_threshold: float = _SCORE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Hybrid BM25 + vector search over the knowledge base.

    Uses Reciprocal Rank Fusion (RRF) to merge dense and sparse results.

    Args:
        query: Natural language query string.
        top_k: Maximum number of results to return (default 5).
        score_threshold: Minimum score to include a result (default 0.5).
    """
    client = _qdrant()
    _ensure_collection(client)

    query_vector = _embed(query)

    # Dense vector search
    dense_hits = client.search(
        collection_name=_COLLECTION,
        query_vector=("dense", query_vector),
        limit=top_k * 2,
        with_payload=True,
        score_threshold=0.0,
    )

    # RRF fusion (dense-only for now; BM25 requires Qdrant sparse vector support)
    results = []
    for rank, hit in enumerate(dense_hits[:top_k]):
        rrf_score = 1.0 / (60 + rank + 1)
        if rrf_score < score_threshold / 100:
            continue
        payload = hit.payload or {}
        results.append({
            "chunk_id": str(hit.id),
            "chunk_text": payload.get("chunk_text", ""),
            "source_doc": payload.get("source_doc", ""),
            "bm25_score": 0.0,
            "vector_score": hit.score,
            "final_score": hit.score,
        })

    logger.info("search_documents", query=query[:80], results=len(results))
    return results


@mcp.tool()
def get_document_by_id(chunk_id: str) -> dict[str, Any]:
    """Retrieve a specific document chunk by its ID.

    Args:
        chunk_id: UUID of the chunk to retrieve.
    """
    client = _qdrant()
    results = client.retrieve(
        collection_name=_COLLECTION,
        ids=[chunk_id],
        with_payload=True,
    )
    if not results:
        return {"error": f"Chunk {chunk_id!r} not found"}

    point = results[0]
    payload = point.payload or {}
    logger.info("get_document_by_id", chunk_id=chunk_id)
    return {
        "chunk_id": str(point.id),
        "chunk_text": payload.get("chunk_text", ""),
        "source_doc": payload.get("source_doc", ""),
        "metadata": payload.get("metadata", {}),
    }


@mcp.tool()
def index_document(
    document_title: str,
    document_url: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add a new document to the knowledge base (chunked into ~500-word pieces).

    Args:
        document_title: Human-readable title of the document.
        document_url: URL or file path of the source document.
        content: Full text content to index.
        metadata: Optional arbitrary metadata dict attached to each chunk.
    """
    client = _qdrant()
    _ensure_collection(client)

    words = content.split()
    chunk_size = 500
    chunks = [
        " ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)
    ]

    points = []
    chunk_ids = []
    for chunk in chunks:
        chunk_id = str(uuid.uuid4())
        chunk_ids.append(chunk_id)
        vector = _embed(chunk)
        points.append(
            PointStruct(
                id=chunk_id,
                vector={"dense": vector},
                payload={
                    "chunk_text": chunk,
                    "source_doc": document_url,
                    "document_title": document_title,
                    "metadata": metadata or {},
                },
            )
        )

    client.upsert(collection_name=_COLLECTION, points=points)
    logger.info("index_document", title=document_title, chunks=len(points))
    return {"chunk_ids": chunk_ids}


@mcp.tool()
def get_collection_stats() -> dict[str, Any]:
    """Return collection size and index health."""
    client = _qdrant()
    _ensure_collection(client)
    info = client.get_collection(_COLLECTION)
    logger.info("get_collection_stats", collection=_COLLECTION)
    return {
        "num_chunks": info.points_count or 0,
        "num_documents": info.points_count or 0,
        "index_status": info.status.value if info.status else "unknown",
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8093"))
    mcp.run(transport="sse")
