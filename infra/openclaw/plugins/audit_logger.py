"""OpenCLAW plugin: write every inbound + outbound message to the audit log.

Calls a small endpoint on the skills service so all log writes go through one
auditable channel rather than each plugin opening its own DB connection.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = os.environ.get("SKILLS_API_BASE_URL", "http://skills:8080")
API_TOKEN = os.environ.get("SKILLS_API_TOKEN", "dev-token")


async def on_message_received(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    await _log(
        direction="in",
        wa_jid=str(message.get("from") or ""),
        body=message.get("text"),
        meta={"raw": message.get("meta", {})},
    )
    return message


async def on_message_sent(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    await _log(
        direction="out",
        wa_jid=str(message.get("to") or ""),
        body=message.get("text"),
        meta={"raw": message.get("meta", {})},
    )
    return message


async def _log(*, direction: str, wa_jid: str, body: str | None, meta: dict[str, Any]) -> None:
    if not wa_jid:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{API_BASE}/message-log",
                headers={"Authorization": f"Bearer {API_TOKEN}"},
                json={"direction": direction, "wa_jid": wa_jid, "body": body, "meta": meta},
            )
    except Exception:
        # Audit log is best-effort; never block the message turn.
        pass
