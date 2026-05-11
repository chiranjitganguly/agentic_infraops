"""Shared ADK Runner factory for calling agents programmatically.

Provides run_agent() — invokes an ADK root_agent with a JSON input dict
and returns the last Event's text content as a parsed dict.

Used by the web backend routers and email dispatcher to call agents
without going over HTTP (in-process A2A pattern).

For cross-service calls (different Docker containers), agents are still
reached via the A2A HTTP endpoint. This helper is for same-process calls.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from google.adk import Runner
from google.adk.agents import BaseAgent
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types


async def run_agent(agent: BaseAgent, input_data: dict[str, Any]) -> dict[str, Any]:
    """Run an ADK agent with input_data and return the parsed JSON response.

    Creates a fresh InMemorySessionService and session per call —
    agents in this project are stateless per-request.

    Args:
        agent: The ADK BaseAgent (root_agent) to invoke.
        input_data: Dict that will be JSON-serialised as the user message.

    Returns:
        Parsed dict from the agent's response Event.
    """
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name=agent.name,
    )

    session = await session_service.create_session(
        app_name=agent.name,
        user_id="system",
    )

    user_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=json.dumps(input_data, default=str))],
    )

    result: dict[str, Any] = {}
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.content and event.content.parts:
            text = event.content.parts[0].text or ""
            if text:
                try:
                    result = json.loads(text)
                except json.JSONDecodeError:
                    result = {"raw": text}

    return result
