"""Thin wrapper around the Anthropic Claude API."""
from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from .settings import get_settings

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def chat_json(
    *,
    model: str | None = None,
    system: str,
    user: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call Claude and require a JSON object response. Robust to surrounding chatter."""
    import json
    import re

    s = get_settings()
    model = model or s.claude_classifier_model
    msg = await _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(part.text for part in msg.content if getattr(part, "type", None) == "text")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"LLM did not return JSON: {raw!r}")
    return json.loads(m.group(0))
