"""Domain models.

The *insight* and *diarization* models are also used as OpenAI structured-output
schemas, so they deliberately avoid default values (strict structured outputs
require every field to be present; optionality is expressed as nullable types).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Transcript (produced by STT, enriched by diarization) ---


class TranscriptSegment(BaseModel):
    text: str
    start: float | None = None
    end: float | None = None
    speaker: str | None = None


class Transcript(BaseModel):
    full_text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str | None = None
    duration: float | None = None

    def speaker_labeled(self) -> bool:
        return bool(self.segments) and all(s.speaker for s in self.segments)

    def as_dialogue(self) -> str:
        if self.segments:
            return "\n".join(
                f"{s.speaker or 'Unknown'}: {s.text.strip()}" for s in self.segments
            )
        return self.full_text


# --- Diarization (LLM structured output) ---


class SpeakerAssignment(BaseModel):
    index: int
    speaker_id: str


class SpeakerName(BaseModel):
    speaker_id: str
    name: str | None


class DiarizationResult(BaseModel):
    assignments: list[SpeakerAssignment]
    names: list[SpeakerName]


# --- Insights (LLM structured output) ---


class Commitment(BaseModel):
    text: str
    owner: str
    due: str | None
    status: str


class Quote(BaseModel):
    speaker: str
    quote: str


class Insights(BaseModel):
    title: str
    summary: str
    date: str | None
    participants: list[str]
    topics: list[str]
    decisions: list[str]
    commitments: list[Commitment]
    action_items: list[str]
    notable_quotes: list[Quote]


# --- API result ---


class ConversationResult(BaseModel):
    conversation_id: str
    insights: Insights
    transcript: Transcript
