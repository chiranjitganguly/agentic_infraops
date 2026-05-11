"""FAQ Agent A2A contract models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    document_title: str
    document_url: str | None = None
    chunk_excerpt: str = Field(max_length=200, description="First 200 chars of matched chunk")
    relevance_score: float = Field(ge=0.0, le=1.0)


class FAQInput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    question: str = Field(min_length=1)
    requesting_user: str = Field(min_length=1)
    max_chunks: int = Field(default=5, ge=1, le=20)


class FAQAnsweredOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["answered"] = "answered"
    answer: str
    sources: list[Source] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    answered_at: datetime


class FAQNoResultsOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["no_results"] = "no_results"
    message: str = (
        "No relevant documentation found for your question. "
        "Consider checking the GCP documentation directly or contacting the platform engineering team."
    )
    answered_at: datetime
