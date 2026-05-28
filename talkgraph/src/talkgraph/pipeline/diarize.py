"""Speaker attribution.

OpenAI transcription does not return speaker labels, so for the MVP we infer
"who said what" from the transcript text with an LLM. This separates speakers by
*what is said*, not by voice, so labels are approximate. The `Diarizer` protocol
lets us swap in acoustic diarization (pyannote / AssemblyAI) later without
touching the rest of the pipeline.
"""

from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI

from ..models import DiarizationResult, Transcript, TranscriptSegment

_SYSTEM = (
    "You are an expert at speaker diarization from raw, unlabeled transcripts. "
    "You are given a conversation as numbered lines. Group the lines by who is "
    "speaking, giving each distinct speaker a stable id like S1, S2, S3. Assign "
    "every line index to exactly one speaker id. If a speaker's real name is "
    "clearly stated or addressed in the conversation, map that id to the name in "
    "`names`; otherwise map it to null. Do not invent names."
)


class Diarizer(Protocol):
    async def diarize(self, transcript: Transcript) -> Transcript: ...


class LLMDiarizer:
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        self._client = client
        self._model = model

    async def diarize(self, transcript: Transcript) -> Transcript:
        if transcript.speaker_labeled():
            return transcript

        segments = transcript.segments or [TranscriptSegment(text=transcript.full_text)]
        numbered = "\n".join(f"[{i}] {s.text.strip()}" for i, s in enumerate(segments))

        completion = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Transcript lines:\n{numbered}"},
            ],
            response_format=DiarizationResult,
        )
        return _apply(segments, completion.choices[0].message.parsed, transcript)


def _apply(
    segments: list[TranscriptSegment],
    result: DiarizationResult,
    transcript: Transcript,
) -> Transcript:
    name_map = {n.speaker_id: n.name for n in result.names if n.name}
    assign = {a.index: a.speaker_id for a in result.assignments}

    # Stable, human-friendly labels in order of first appearance.
    labels: dict[str, str] = {}
    counter = 0
    for i in range(len(segments)):
        sid = assign.get(i)
        if sid is None or sid in labels:
            continue
        if sid in name_map:
            labels[sid] = name_map[sid]
        else:
            counter += 1
            labels[sid] = f"Speaker {counter}"

    new_segments = [
        TranscriptSegment(
            text=s.text,
            start=s.start,
            end=s.end,
            speaker=labels.get(assign.get(i), "Unknown"),
        )
        for i, s in enumerate(segments)
    ]
    return Transcript(
        full_text=transcript.full_text,
        segments=new_segments,
        language=transcript.language,
        duration=transcript.duration,
    )
