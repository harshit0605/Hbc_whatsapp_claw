"""OpenCLAW plugin: detect inbound language; stash on the session and (best-
effort) persist to the resident record so the LLM gets the right hint even
after a session restart.
"""
from __future__ import annotations

from typing import Any

try:
    from langdetect import DetectorFactory, detect_langs

    DetectorFactory.seed = 0
except Exception:  # pragma: no cover
    detect_langs = None  # type: ignore[assignment]


SUPPORTED = {"en", "hi", "mr", "ta", "te", "kn", "bn", "gu", "pa"}


async def on_message_received(ctx: Any, message: dict[str, Any]) -> dict[str, Any]:
    body: str = (message.get("text") or "").strip()
    if not body:
        return message

    locale: str | None = None
    if detect_langs is not None:
        try:
            guesses = detect_langs(body)
            best = guesses[0] if guesses else None
            if best and best.lang in SUPPORTED and best.prob >= 0.85:
                locale = best.lang
        except Exception:
            pass
    if locale is None and any("ऀ" <= c <= "ॿ" for c in body):
        locale = "hi"

    if locale:
        ctx.session.locale = locale
        # Inline the hint into message meta so the LLM always sees it even if
        # OpenCLAW's prompt-time interpolation of {{session.locale}} is off.
        message.setdefault("meta", {})["detected_locale"] = locale
    return message
