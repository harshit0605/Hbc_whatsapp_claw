"""LLM-backed classification: pick category + severity + short title."""
from __future__ import annotations

import os
from typing import Any

from .llm import chat_json
from .models import ClassificationOut

SYSTEM = """You are a maintenance ticket classifier for a residential housing society.
Given a resident's complaint (which may be in English, Hindi, Hinglish, or other Indian
languages, possibly transcribed from voice), output a strict JSON object with these keys:

  category:   one of plumbing, electrical, lift, cleanliness, garbage, security,
              water, gas, carpentry, pest_control, common_area, other
  severity:   one of low, medium, high, critical
  title:      a short English title (<=8 words) summarizing the issue
  confidence: a number between 0 and 1
  rationale:  one short English sentence explaining the classification

Severity rubric:
  - critical: immediate threat to life or property — gas leak, fire, flooding,
              live exposed wires, person trapped in lift, structural collapse
  - high:     significant disruption — full power outage in flat, no water,
              sewage backflow, lift out of service in a high-rise tower
  - medium:   meaningful nuisance — clogged drain, faulty switch, garbage piling
  - low:      minor / cosmetic — flickering bulb, small leak, paint peeling

Return ONLY the JSON object, no preamble."""


async def classify(text: str, media_descriptions: list[str] | None = None) -> ClassificationOut:
    """Classify a complaint. Falls back to a heuristic if the LLM is unavailable."""
    md = ""
    if media_descriptions:
        md = "\n\nAttached media descriptions:\n- " + "\n- ".join(media_descriptions)
    user = f"Complaint:\n{text}{md}"

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or "replace-me" in api_key:
        return _heuristic_classify(text)

    try:
        raw = await chat_json(system=SYSTEM, user=user, max_tokens=256)
    except Exception:
        return _heuristic_classify(text)

    return _validate(raw)


def _validate(raw: dict[str, Any]) -> ClassificationOut:
    return ClassificationOut(
        category=raw.get("category", "other"),
        severity=raw.get("severity", "low"),
        title=str(raw.get("title", "Maintenance issue"))[:120],
        confidence=float(raw.get("confidence", 0.5)),
        rationale=raw.get("rationale"),
    )


# ─── Heuristic fallback (only used when the Claude API is unreachable) ──────
_KEYWORDS: list[tuple[str, str, str]] = [
    # (keyword, category, severity)
    ("gas leak", "gas", "critical"),
    ("fire", "security", "critical"),
    ("trapped", "lift", "critical"),
    ("phas gaya", "lift", "critical"),
    ("flood", "water", "critical"),
    ("paani bhar gaya", "water", "critical"),
    ("short circuit", "electrical", "critical"),
    ("no water", "water", "high"),
    ("paani nahi", "water", "high"),
    ("no power", "electrical", "high"),
    ("bijli nahi", "electrical", "high"),
    ("lift not working", "lift", "high"),
    ("lift band", "lift", "high"),
    ("sewage", "plumbing", "high"),
    ("leak", "plumbing", "medium"),
    ("clog", "plumbing", "medium"),
    ("garbage", "garbage", "medium"),
    ("kachra", "garbage", "medium"),
    ("dustbin", "garbage", "medium"),
    ("dirty", "cleanliness", "low"),
    ("ganda", "cleanliness", "low"),
    ("bulb", "electrical", "low"),
    ("switch", "electrical", "low"),
    ("pest", "pest_control", "medium"),
    ("cockroach", "pest_control", "medium"),
    ("rat", "pest_control", "medium"),
    ("door", "carpentry", "low"),
    ("lock", "security", "medium"),
]


def _heuristic_classify(text: str) -> ClassificationOut:
    lower = text.lower()
    best: tuple[str, str] = ("other", "low")
    for kw, cat, sev in _KEYWORDS:
        if kw in lower:
            best = (cat, sev)
            break
    return ClassificationOut(
        category=best[0],  # type: ignore[arg-type]
        severity=best[1],  # type: ignore[arg-type]
        title=text[:60].strip() or "Maintenance issue",
        confidence=0.4,
        rationale="heuristic-classifier fallback",
    )
