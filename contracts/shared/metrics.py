"""Shared Prometheus metrics registry.

Import this module to get pre-registered metrics. Each service should call
start_metrics_server() once at startup.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server


# ─── Provisioning ─────────────────────────────────────────────────────────────
provisioning_job_total = Counter(
    "provisioning_job_total",
    "Total provisioning jobs by status and resource type",
    labelnames=["status", "resource_type"],
)

# ─── Intent Classification ────────────────────────────────────────────────────
intent_classification_duration_seconds = Histogram(
    "intent_classification_duration_seconds",
    "Time spent classifying user intent via LiteLLM",
    labelnames=["channel"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

intent_classification_total = Counter(
    "intent_classification_total",
    "Total intent classification calls by outcome",
    labelnames=["intent", "outcome"],
)

# ─── Circuit Breaker ──────────────────────────────────────────────────────────
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=half-open, 2=open",
    labelnames=["tool", "resource_type"],
)

# ─── API / Web Backend ────────────────────────────────────────────────────────
api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "HTTP request duration by method, path, and status code",
    labelnames=["method", "path", "status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

api_auth_failures_total = Counter(
    "api_auth_failures_total",
    "Total API authentication failures by reason",
    labelnames=["reason"],
)

# ─── A2A Agent Tasks ─────────────────────────────────────────────────────────
a2a_task_duration_seconds = Histogram(
    "a2a_task_duration_seconds",
    "Time spent processing an A2A task",
    labelnames=["agent", "outcome"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
)

a2a_task_total = Counter(
    "a2a_task_total",
    "Total A2A task calls by agent and outcome",
    labelnames=["agent", "outcome"],
)

# ─── FAQ ─────────────────────────────────────────────────────────────────────
faq_retrieval_duration_seconds = Histogram(
    "faq_retrieval_duration_seconds",
    "Time spent on hybrid Qdrant document retrieval",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

faq_answer_duration_seconds = Histogram(
    "faq_answer_duration_seconds",
    "Time spent generating FAQ answer via LiteLLM",
    buckets=[1.0, 5.0, 10.0, 20.0, 60.0],
)


def start_metrics_server(port: int = 9100) -> None:
    """Start the Prometheus /metrics HTTP server on the given port."""
    start_http_server(port)
