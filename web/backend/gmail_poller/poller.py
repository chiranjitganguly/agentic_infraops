"""T056 — Gmail polling loop.

Polls Gmail for unread messages every 30 seconds using history.list() incremental sync.
Skips auto-replies. Detects confirmation replies vs new requests.
Dispatches accordingly via dispatcher.py.
"""
from __future__ import annotations

import asyncio
import os

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="gmail-poller")
logger = get_logger("gmail-poller")

_POLL_INTERVAL = 30
_HISTORY_ID_FILE = "/tmp/gmail_history_id.txt"

_CONFIRMATION_KEYWORDS = {"confirm", "yes", "approve"}


def _load_history_id() -> str | None:
    try:
        with open(_HISTORY_ID_FILE) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _save_history_id(history_id: str) -> None:
    with open(_HISTORY_ID_FILE, "w") as f:
        f.write(history_id)


def _is_confirmation_text(body: str) -> bool:
    lower = body.lower()
    return any(kw in lower for kw in _CONFIRMATION_KEYWORDS)


async def _poll_once(confirmation_threads: dict[str, str]) -> None:
    """Single poll iteration.

    confirmation_threads: maps thread_id → infra_request_id for pending confirmations.
    """
    from mcp_servers.gmail import server as gmail
    from web.backend.gmail_poller.dispatcher import (
        dispatch_confirmation_reply,
        dispatch_email_request,
    )

    history_id = _load_history_id()

    result = gmail.poll_unread_messages(history_id=history_id)
    messages = result.get("messages", [])
    new_history_id = result.get("new_history_id")

    if new_history_id:
        _save_history_id(new_history_id)

    for message in messages:
        message_id = message.get("id") or message.get("message_id")
        thread_id = message.get("thread_id")

        try:
            auto_reply_result = gmail.is_auto_reply(message_id=message_id)
            if auto_reply_result.get("is_auto_reply"):
                logger.info("gmail_auto_reply_skipped", message_id=message_id)
                gmail.mark_as_read(message_id=message_id)
                continue

            if thread_id and thread_id in confirmation_threads:
                infra_request_id = confirmation_threads[thread_id]
                body = message.get("body", "")
                if _is_confirmation_text(body):
                    await dispatch_confirmation_reply(message=message, infra_request_id=infra_request_id)
                    del confirmation_threads[thread_id]
                else:
                    logger.info("gmail_thread_reply_not_confirmation", thread_id=thread_id)
            else:
                new_thread_id = await dispatch_email_request(message=message)
                if new_thread_id and isinstance(new_thread_id, tuple):
                    sent_thread_id, infra_request_id = new_thread_id
                    if sent_thread_id:
                        confirmation_threads[sent_thread_id] = infra_request_id

            gmail.mark_as_read(message_id=message_id)

        except Exception as exc:
            logger.error("gmail_poll_message_error", message_id=message_id, error=str(exc))


async def run_poller() -> None:
    confirmation_threads: dict[str, str] = {}
    logger.info("gmail_poller_started", interval=_POLL_INTERVAL)

    while True:
        try:
            await _poll_once(confirmation_threads)
        except Exception as exc:
            logger.error("gmail_poll_error", error=str(exc))

        await asyncio.sleep(_POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_poller())
