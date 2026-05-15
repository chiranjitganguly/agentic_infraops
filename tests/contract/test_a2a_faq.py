"""T076 — Contract tests for FAQ Agent A2A schemas.

Validates FAQInput, FAQAnsweredOutput, FAQNoResultsOutput, Source models.
No external services required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.agents.faq import FAQAnsweredOutput, FAQInput, FAQNoResultsOutput, Source


@pytest.mark.contract
class TestFAQInput:
    def test_valid_minimal(self) -> None:
        inp = FAQInput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            question="What is the best practice for VPC design on GCP?",
            requesting_user="dev@example.com",
        )
        assert inp.max_chunks == 5

    def test_valid_with_max_chunks(self) -> None:
        inp = FAQInput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            question="How should I configure IAM?",
            requesting_user="user@example.com",
            max_chunks=10,
        )
        assert inp.max_chunks == 10

    def test_max_chunks_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FAQInput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                question="question",
                requesting_user="user@example.com",
                max_chunks=25,
            )

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValidationError):
            FAQInput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                question="",
                requesting_user="user@example.com",
            )

    def test_empty_requesting_user_raises(self) -> None:
        with pytest.raises(ValidationError):
            FAQInput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                question="What is GCP?",
                requesting_user="",
            )

    def test_serialises_to_json(self) -> None:
        inp = FAQInput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            question="Best GCP VPC design?",
            requesting_user="dev@example.com",
        )
        dumped = inp.model_dump(mode="json")
        assert isinstance(dumped["correlation_id"], str)
        assert dumped["question"] == "Best GCP VPC design?"


@pytest.mark.contract
class TestSource:
    def test_valid_source(self) -> None:
        s = Source(
            document_title="GCP VPC Best Practices",
            document_url="https://cloud.google.com/vpc/docs",
            chunk_excerpt="Use VPC shared networks for org-wide connectivity.",
            relevance_score=0.87,
        )
        assert s.document_title == "GCP VPC Best Practices"
        assert s.relevance_score == pytest.approx(0.87)

    def test_document_url_optional(self) -> None:
        s = Source(
            document_title="Internal Guide",
            chunk_excerpt="Some guidance here.",
            relevance_score=0.6,
        )
        assert s.document_url is None

    def test_relevance_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Source(
                document_title="Doc",
                chunk_excerpt="text",
                relevance_score=1.5,
            )

    def test_chunk_excerpt_max_length(self) -> None:
        long_text = "x" * 201
        with pytest.raises(ValidationError):
            Source(
                document_title="Doc",
                chunk_excerpt=long_text,
                relevance_score=0.5,
            )

    def test_serialises_to_json(self) -> None:
        s = Source(
            document_title="IAM Guide",
            chunk_excerpt="Least privilege principle.",
            relevance_score=0.9,
        )
        dumped = s.model_dump(mode="json")
        assert dumped["document_title"] == "IAM Guide"
        assert dumped["relevance_score"] == pytest.approx(0.9)


@pytest.mark.contract
class TestFAQAnsweredOutput:
    _NOW = datetime.now(timezone.utc)

    def _make_source(self) -> Source:
        return Source(
            document_title="GCP Docs",
            chunk_excerpt="Network best practices.",
            relevance_score=0.85,
        )

    def test_valid_answered(self) -> None:
        out = FAQAnsweredOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answer="Use VPC shared networks for organisation-wide connectivity.",
            sources=[self._make_source()],
            answered_at=self._NOW,
        )
        assert out.status == "answered"
        assert out.answer != ""
        assert len(out.sources) == 1

    def test_confidence_optional(self) -> None:
        out = FAQAnsweredOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answer="Some answer.",
            sources=[self._make_source()],
            answered_at=self._NOW,
        )
        assert out.confidence is None

    def test_confidence_with_value(self) -> None:
        out = FAQAnsweredOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answer="Answer.",
            sources=[self._make_source()],
            confidence=0.91,
            answered_at=self._NOW,
        )
        assert out.confidence == pytest.approx(0.91)

    def test_sources_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            FAQAnsweredOutput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                answer="Answer without sources.",
                sources=[],
                answered_at=self._NOW,
            )

    def test_serialises_to_json(self) -> None:
        out = FAQAnsweredOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answer="VPC best practice is subnet isolation.",
            sources=[self._make_source()],
            answered_at=self._NOW,
        )
        dumped = out.model_dump(mode="json")
        assert dumped["status"] == "answered"
        assert isinstance(dumped["sources"], list)
        assert len(dumped["sources"]) == 1


@pytest.mark.contract
class TestFAQNoResultsOutput:
    _NOW = datetime.now(timezone.utc)

    def test_default_status_and_message(self) -> None:
        out = FAQNoResultsOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answered_at=self._NOW,
        )
        assert out.status == "no_results"
        assert "No relevant documentation" in out.message

    def test_serialises_to_json(self) -> None:
        out = FAQNoResultsOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            answered_at=self._NOW,
        )
        dumped = out.model_dump(mode="json")
        assert dumped["status"] == "no_results"
        assert isinstance(dumped["answered_at"], str)
