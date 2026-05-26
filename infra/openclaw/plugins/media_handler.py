"""OpenCLAW plugin: download inbound media and stash it in object storage.

On every inbound message that contains a `<media:image>`, `<media:audio>`, or
`<media:document>` placeholder, this plugin:

1. Calls the OpenCLAW gateway helper to retrieve the binary.
2. Uploads it via the skills service's POST /media endpoint.
3. Replaces the placeholder in the message body with a token of the form
   `[storage:<kind>:<key>]` so the LLM sees an opaque, safe reference.

The agent then passes those keys to `create_complaint` as `media_storage_keys`.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

_TOKEN_RE = re.compile(r"<media:(image|audio|video|document)(?::([^>]+))?>")

API_BASE = os.environ.get("SKILLS_API_BASE_URL", "http://skills:8080")
API_TOKEN = os.environ.get("SKILLS_API_TOKEN", "dev-token")


async def on_message_received(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    body: str = message.get("text") or ""
    matches = list(_TOKEN_RE.finditer(body))
    if not matches:
        return message

    new_tokens: list[str] = []
    for m in matches:
        kind = m.group(1)
        # OpenCLAW exposes the binary via ctx.media.download(<token>) when the
        # plugin is opted into hooks; signature varies by version. We try both
        # the new and the legacy APIs.
        data = await _fetch_media(ctx, m.group(0))
        if data is None:
            new_tokens.append(m.group(0))  # leave placeholder; agent will skip it
            continue
        mime, blob = data
        key = await _upload(kind=kind, mime=mime, blob=blob)
        token = f"[storage:{kind}:{key}]"
        new_tokens.append(token)

    # Substitute each match in order.
    body_iter = iter(new_tokens)
    new_body = _TOKEN_RE.sub(lambda _m: next(body_iter), body)
    message["text"] = new_body

    # Also expose structured list for tools that want it directly.
    stored = message.setdefault("storage_keys", [])
    for tok in new_tokens:
        if tok.startswith("[storage:"):
            kind, key = tok[len("[storage:"):-1].split(":", 1)
            stored.append({"kind": kind, "storage_key": key})
    return message


async def _fetch_media(ctx: Any, token: str) -> tuple[str | None, bytes] | None:
    for attr in ("media", "channel", "whatsapp"):
        obj = getattr(ctx, attr, None)
        if obj and hasattr(obj, "download"):
            try:
                result = await obj.download(token)
            except Exception:
                continue
            if isinstance(result, tuple):
                return result  # (mime, bytes)
            return None, result
    return None


async def _upload(*, kind: str, mime: str | None, blob: bytes) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}/media",
            params={"kind": kind},
            headers={"Authorization": f"Bearer {API_TOKEN}"},
            files={"file": ("upload.bin", blob, mime or "application/octet-stream")},
        )
        resp.raise_for_status()
        return resp.json()["storage_key"]
