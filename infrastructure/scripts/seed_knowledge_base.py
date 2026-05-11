"""Seed Qdrant knowledge base from Markdown documents.

Chunks Markdown files from docs/knowledge/ and indexes them into the
Qdrant collection `infraops_knowledge_base` using hybrid BM25 + dense
vectors via LiteLLM gateway for embedding.

Usage:
    python infrastructure/scripts/seed_knowledge_base.py
    python infrastructure/scripts/seed_knowledge_base.py --knowledge-dir /path/to/docs
    python infrastructure/scripts/seed_knowledge_base.py --recreate-collection
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Iterator

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)


KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "docs" / "knowledge"
COLLECTION_NAME = "infraops_knowledge_base"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
DENSE_VECTOR_SIZE = 768
SCORE_THRESHOLD = 0.5


def chunk_markdown(text: str, source_doc: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterator[dict]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        if not chunk_words:
            continue
        chunk_text = " ".join(chunk_words)
        chunk_id = hashlib.sha256(f"{source_doc}:{i}:{chunk_text}".encode()).hexdigest()
        yield {
            "id": str(uuid.UUID(chunk_id[:32])),
            "chunk_text": chunk_text,
            "source_doc": source_doc,
            "chunk_index": i // step,
        }


async def embed_text(text: str, litellm_url: str, master_key: str, embedding_model: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{litellm_url}/embeddings",
            headers={"Authorization": f"Bearer {master_key}"},
            json={"model": embedding_model, "input": text},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


async def seed(knowledge_dir: Path, recreate: bool = False) -> None:
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    litellm_url = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")
    embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

    client = AsyncQdrantClient(url=qdrant_url)

    collections = await client.get_collections()
    exists = any(c.name == COLLECTION_NAME for c in collections.collections)

    if recreate and exists:
        print(f"Deleting existing collection '{COLLECTION_NAME}'...")
        await client.delete_collection(COLLECTION_NAME)
        exists = False

    if not exists:
        print(f"Creating collection '{COLLECTION_NAME}'...")
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": VectorParams(size=DENSE_VECTOR_SIZE, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
        )

    md_files = sorted(knowledge_dir.glob("**/*.md"))
    if not md_files:
        print(f"No Markdown files found in {knowledge_dir}", file=sys.stderr)
        return

    total_chunks = 0
    for md_file in md_files:
        source_doc = str(md_file.relative_to(knowledge_dir))
        text = md_file.read_text(encoding="utf-8")
        chunks = list(chunk_markdown(text, source_doc))

        print(f"Indexing {source_doc} → {len(chunks)} chunks")
        points: list[PointStruct] = []
        for chunk in chunks:
            dense_vec = await embed_text(chunk["chunk_text"], litellm_url, master_key, embedding_model)
            points.append(
                PointStruct(
                    id=chunk["id"],
                    vector={"dense": dense_vec},
                    payload={
                        "chunk_text": chunk["chunk_text"],
                        "source_doc": chunk["source_doc"],
                        "chunk_index": chunk["chunk_index"],
                    },
                )
            )

        await client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_chunks += len(chunks)

    print(f"\nSeeding complete. {len(md_files)} file(s), {total_chunks} chunk(s) indexed into '{COLLECTION_NAME}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Qdrant knowledge base from Markdown files")
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    parser.add_argument("--recreate-collection", action="store_true", help="Drop and recreate the Qdrant collection before seeding")
    args = parser.parse_args()
    asyncio.run(seed(args.knowledge_dir, recreate=args.recreate_collection))


if __name__ == "__main__":
    main()
