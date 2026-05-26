"""OpenCLAW plugin: tag inbound messages from known workers.

Sets `ctx.session.is_worker = True` and `ctx.session.worker_wa_jid = <jid>`
when the sender's JID matches a row in the `worker` table. The system prompt
then routes the agent into the worker flow (ACCEPT / DONE / HELP).

We resolve via the skills HTTP API rather than the DB so the plugin stays
stateless and credential-free.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = os.environ.get("SKILLS_API_BASE_URL", "http://skills:8080")
API_TOKEN = os.environ.get("SKILLS_API_TOKEN", "dev-token")


async def on_message_received(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    jid = str(message.get("from") or "")
    if not jid:
        return message
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{API_BASE}/workers/lookup",
                params={"wa_jid": jid},
                headers={"Authorization": f"Bearer {API_TOKEN}"},
            )
        if resp.status_code == 200:
            ctx.session.is_worker = True
            ctx.session.worker_wa_jid = jid
            ctx.session.worker = resp.json()
    except Exception:
        pass
    return message
