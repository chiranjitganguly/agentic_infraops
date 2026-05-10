"""T040 — gmail-mcp: MCP server wrapping the Gmail API for inbound/outbound email.

Tools: poll_unread_messages, get_message, get_thread_messages,
       send_email, mark_as_read, is_auto_reply.

Uses history.list() incremental sync after the first poll.
Auto-reply detection checks X-Autoreply, Auto-Submitted, X-Auto-Response-Suppress headers.
"""
from __future__ import annotations

import base64
import os
import re
from email.mime.text import MIMEText
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient import discovery
from mcp.server.fastmcp import FastMCP

from agentic_infraops.contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="gmail-mcp")
logger = get_logger("gmail-mcp")

mcp = FastMCP("gmail-mcp")

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

_AUTO_REPLY_HEADERS = {"x-autoreply", "auto-submitted", "x-auto-response-suppress"}
_CONFIRMATION_KEYWORDS = re.compile(r"\b(confirm|yes|approve)\b", re.IGNORECASE)

_gmail_service: Any = None


def _get_gmail_service() -> Any:
    global _gmail_service
    if _gmail_service is not None:
        return _gmail_service

    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "")
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "")

    creds: Credentials | None = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                f"Gmail credentials not found or invalid. "
                f"Ensure {token_path} exists with a valid OAuth2 token."
            )

    _gmail_service = discovery.build("gmail", "v1", credentials=creds)
    return _gmail_service


def _parse_message(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    body = ""
    parts = payload.get("parts", [])
    if parts:
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    return {
        "message_id": raw.get("id", ""),
        "thread_id": raw.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "body": body,
        "snippet": raw.get("snippet", ""),
        "label_ids": raw.get("labelIds", []),
        "headers": headers,
    }


@mcp.tool()
def poll_unread_messages(history_id: str | None = None) -> dict[str, Any]:
    """Get unread messages since the last historyId using incremental sync.

    On the first call (no history_id), returns all current unread messages.
    Subsequent calls use history.list() for efficiency.

    Args:
        history_id: The historyId from the previous poll response, or None for first poll.
    """
    service = _get_gmail_service()
    messages: list[dict[str, Any]] = []
    new_history_id = history_id

    if history_id:
        try:
            history_resp = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                )
                .execute()
            )
            new_history_id = history_resp.get("historyId", history_id)
            added_messages = []
            for record in history_resp.get("history", []):
                for msg in record.get("messagesAdded", []):
                    added_messages.append(msg["message"]["id"])

            for msg_id in added_messages:
                raw = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                if "UNREAD" in raw.get("labelIds", []):
                    messages.append(_parse_message(raw))
        except Exception:
            history_id = None

    if not history_id:
        list_resp = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=50)
            .execute()
        )
        new_history_id = list_resp.get("historyId", "")
        for item in list_resp.get("messages", []):
            raw = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            messages.append(_parse_message(raw))

    logger.info("gmail_poll_completed", message_count=len(messages))
    return {"messages": messages, "new_history_id": new_history_id or ""}


@mcp.tool()
def get_message(message_id: str) -> dict[str, Any]:
    """Fetch a full Gmail message by ID.

    Args:
        message_id: The Gmail message ID.
    """
    service = _get_gmail_service()
    raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    return _parse_message(raw)


@mcp.tool()
def get_thread_messages(thread_id: str) -> list[dict[str, Any]]:
    """Fetch all messages in a Gmail thread in chronological order.

    Args:
        thread_id: The Gmail thread ID.
    """
    service = _get_gmail_service()
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    return [_parse_message(msg) for msg in thread.get("messages", [])]


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
) -> dict[str, str]:
    """Send an email via Gmail.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text email body.
        thread_id: Optional thread ID to reply within an existing thread.
        in_reply_to: Optional Message-ID header value for threading.
    """
    service = _get_gmail_service()
    mime_msg = MIMEText(body, "plain")
    mime_msg["to"] = to
    mime_msg["subject"] = subject
    if in_reply_to:
        mime_msg["In-Reply-To"] = in_reply_to
        mime_msg["References"] = in_reply_to

    raw_bytes = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
    send_body: dict[str, Any] = {"raw": raw_bytes}
    if thread_id:
        send_body["threadId"] = thread_id

    result = service.users().messages().send(userId="me", body=send_body).execute()
    logger.info("gmail_email_sent", to=to, message_id=result.get("id"))
    return {
        "message_id": result.get("id", ""),
        "thread_id": result.get("threadId", ""),
    }


@mcp.tool()
def mark_as_read(message_id: str) -> dict[str, bool]:
    """Mark a Gmail message as read by removing the UNREAD label.

    Args:
        message_id: The Gmail message ID to mark as read.
    """
    service = _get_gmail_service()
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    logger.info("gmail_marked_as_read", message_id=message_id)
    return {"success": True}


@mcp.tool()
def is_auto_reply(message_id: str) -> dict[str, bool]:
    """Detect whether a Gmail message is an auto-reply.

    Checks X-Autoreply, Auto-Submitted, and X-Auto-Response-Suppress headers.

    Args:
        message_id: The Gmail message ID to inspect.
    """
    service = _get_gmail_service()
    raw = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
    headers = {
        h["name"].lower(): h["value"].lower()
        for h in raw.get("payload", {}).get("headers", [])
    }

    for header_name in _AUTO_REPLY_HEADERS:
        value = headers.get(header_name, "")
        if value and value not in {"no", "false", "suppress-none"}:
            logger.info("gmail_auto_reply_detected", message_id=message_id, header=header_name)
            return {"is_auto_reply": True}

    return {"is_auto_reply": False}


if __name__ == "__main__":
    mcp.run()
