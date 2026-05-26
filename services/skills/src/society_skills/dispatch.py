"""Outbound WhatsApp delivery via the OpenCLAW gateway.

OpenCLAW exposes an HTTP outbound endpoint that the skills service can call to
push a message to a specific JID. The exact endpoint shape varies by OpenCLAW
plugin version; here we use a small adapter so swapping it out is one file.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .logging_setup import get_logger
from .settings import get_settings

log = get_logger("dispatch")


class OutboundError(RuntimeError):
    pass


async def send_text(
    *,
    to_jid: str,
    body: str,
    quoted_message_id: str | None = None,
    media_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Send a WhatsApp text (with optional image attachments) to a JID.

    `media_urls` should be publicly fetchable URLs (e.g. S3 presigned). The
    OpenCLAW gateway downloads them and forwards them as WhatsApp media.
    """
    s = get_settings()
    payload: dict[str, Any] = {
        "to": to_jid,
        "text": body,
    }
    if quoted_message_id:
        payload["quoted_id"] = quoted_message_id
    if media_urls:
        payload["media"] = [{"url": u} for u in media_urls]

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    ):
        with attempt:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    s.openclaw_outbound_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {s.openclaw_outbound_token}"},
                )
            if resp.status_code >= 400:
                raise OutboundError(
                    f"OpenCLAW outbound failed [{resp.status_code}]: {resp.text}"
                )
            return resp.json() if resp.content else {"ok": True}
    raise OutboundError("unreachable")  # pragma: no cover


async def broadcast_admin_alert(body: str) -> list[dict[str, Any]]:
    s = get_settings()
    results: list[dict[str, Any]] = []
    for jid in s.admin_alert_jid_list:
        try:
            r = await send_text(to_jid=jid, body=body)
            results.append({"jid": jid, "ok": True, "resp": r})
        except Exception as e:
            log.warning("admin_alert_failed", jid=jid, error=str(e))
            results.append({"jid": jid, "ok": False, "error": str(e)})
    return results
