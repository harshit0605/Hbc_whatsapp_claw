from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI

from ..models import Transcript, TranscriptSegment

# Models that return verbose_json with segment timestamps.
_SEGMENT_MODELS = {"whisper-1"}


class STTProvider(Protocol):
    async def transcribe(self, audio_path: str) -> Transcript: ...


class OpenAISTTProvider:
    def __init__(self, client: AsyncOpenAI, model: str = "whisper-1"):
        self._client = client
        self._model = model

    async def transcribe(self, audio_path: str) -> Transcript:
        kwargs: dict = {"model": self._model}
        if self._model in _SEGMENT_MODELS:
            kwargs["response_format"] = "verbose_json"
            kwargs["timestamp_granularities"] = ["segment"]
        with open(audio_path, "rb") as fh:
            resp = await self._client.audio.transcriptions.create(file=fh, **kwargs)
        return _to_transcript(resp)


def _to_transcript(resp) -> Transcript:
    segments: list[TranscriptSegment] = []
    for s in getattr(resp, "segments", None) or []:
        segments.append(
            TranscriptSegment(
                text=(getattr(s, "text", "") or "").strip(),
                start=getattr(s, "start", None),
                end=getattr(s, "end", None),
            )
        )
    full_text = (getattr(resp, "text", "") or "").strip()
    if not segments and full_text:
        segments = [TranscriptSegment(text=full_text)]
    if not full_text and segments:
        full_text = " ".join(s.text for s in segments)
    return Transcript(
        full_text=full_text,
        segments=segments,
        language=getattr(resp, "language", None),
        duration=getattr(resp, "duration", None),
    )
