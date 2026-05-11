"""FAQQuery Pydantic models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_text: str
    source_doc: str
    bm25_score: float = Field(ge=0.0)
    vector_score: float = Field(ge=0.0)
    final_score: float = Field(ge=0.0)
    chunk_id: str | None = None


class FAQQueryCreate(BaseModel):
    correlation_id: uuid.UUID
    raw_question: str = Field(min_length=1)
    requesting_user: str = Field(min_length=1)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    generated_answer: str = ""
    sources_cited: list[dict[str, Any]] = Field(default_factory=list)
    answer_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    no_results_found: bool = False


class FAQQuery(BaseModel):
    id: uuid.UUID
    correlation_id: uuid.UUID
    raw_question: str
    requesting_user: str
    retrieved_chunks: list[RetrievedChunk]
    generated_answer: str
    sources_cited: list[dict[str, Any]]
    answer_confidence: float | None = None
    no_results_found: bool
    created_at: datetime

    model_config = {"from_attributes": True}
