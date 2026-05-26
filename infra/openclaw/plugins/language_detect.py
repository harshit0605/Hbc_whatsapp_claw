"""OpenCLAW plugin: detect inbound language and stash it on the session.

Runs on the `messageReceived` hook. Sets `session.locale` to a 2-letter ISO
code so the agent system prompt can adapt. Conservative: only switches if
confidence is high; otherwise leaves the existing locale alone.
"""
from __future__ import annotations

from typing import Any

try:
    from langdetect import DetectorFactory, detect_langs

    DetectorFactory.seed = 0
except Exception:  # pragma: no cover
    detect_langs = None  # type: ignore[assignment]


# OpenCLAW expects each plugin file to expose async `on_message_received` and
# optionally `on_message_sent`. The exact signature is flexible; we accept the
# generic envelope and mutate `ctx.session`.


SUPPORTED = {"en", "hi", "mr", "ta", "te", "kn", "bn", "gu", "pa"}


async def on_message_received(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    body: str = (message.get("text") or "").strip()
    if not body or detect_langs is None:
        return message

    try:
        guesses = detect_langs(body)
    except Exception:
        return message

    best = guesses[0] if guesses else None
    if best and best.lang in SUPPORTED and best.prob >= 0.85:
        ctx.session.locale = best.lang
    elif body and any("ऀ" <= c <= "ॿ" for c in body):
        ctx.session.locale = "hi"
    return message
