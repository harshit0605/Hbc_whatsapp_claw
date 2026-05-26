"""OpenCLAW plugin: belt-and-suspenders critical-alert fan-out.

The skills service already auto-escalates from inside `create_complaint` when
severity == 'critical'. This plugin is a second layer that watches outbound
agent messages for a `[CRITICAL_TICKET:<id>]` marker — the agent can emit
this in its reply to the resident, and we forward an alert to admins even if
the MCP-side escalation failed.

Idempotent: dedupes by ticket id within a 10-minute window so a chatty agent
doesn't spam admins.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

API_BASE = os.environ.get("SKILLS_API_BASE_URL", "http://skills:8080")
API_TOKEN = os.environ.get("SKILLS_API_TOKEN", "dev-token")

_MARKER = re.compile(r"\[CRITICAL_TICKET:([0-9a-fA-F-]{36})\]")
_seen: dict[str, float] = {}  # complaint_id → last alert epoch seconds
_DEDUP_WINDOW = 600  # 10 min


async def on_message_sent(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    body: str = message.get("text") or ""
    match = _MARKER.search(body)
    if not match:
        return message
    cid = match.group(1)
    now = time.time()
    last = _seen.get(cid, 0)
    if now - last < _DEDUP_WINDOW:
        return message
    _seen[cid] = now

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{API_BASE}/admin/test-alert",
                headers={"Authorization": f"Bearer {API_TOKEN}"},
                json={
                    "body": (
                        f"🚨 Critical ticket flagged by agent (id={cid}). "
                        f"Open the admin portal to triage."
                    )
                },
            )
    except Exception:
        pass
    return message
