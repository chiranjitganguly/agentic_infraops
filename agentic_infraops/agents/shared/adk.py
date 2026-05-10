"""Utilities for building Google ADK-compatible responses."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Iterable, Sequence


def build_agent_card(
    *,
    name: str,
    description: str,
    version: str,
    url: str,
    capabilities: Sequence[str],
    input_schema: str,
    output_schema: str,
) -> dict[str, object]:
    """Construct an agent card adhering to the documented ADK schema."""
    return {
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "protocol": "google-adk/a2a-v1",
        "capabilities": list(capabilities),
        "inputSchema": input_schema,
        "outputSchema": output_schema,
    }


def _timestamp_ms(offset_ms: int = 0) -> str:
    moment = datetime.now(timezone.utc) + timedelta(milliseconds=offset_ms)
    return moment.isoformat()


def build_status(states: Iterable[str]) -> dict[str, object]:
    """Return ADK task status with a simple submitted→… timeline."""
    timeline = list(states)
    if not timeline:
        timeline = ["completed"]
    history = [{"state": state, "timestamp": _timestamp_ms(idx * 5)} for idx, state in enumerate(timeline)]
    return {"state": timeline[-1], "history": history}


def build_artifact(payload: dict[str, object]) -> dict[str, object]:
    return {"parts": [{"type": "application/json", "data": payload}]}


def build_task_response(
    *,
    task_id: str,
    payload: dict[str, object],
    states: Sequence[str],
) -> dict[str, object]:
    return {
        "id": task_id,
        "status": build_status(states),
        "artifacts": [build_artifact(payload)],
    }
