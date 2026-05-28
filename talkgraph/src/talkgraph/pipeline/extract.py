from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI

from ..models import Insights, Transcript

_SYSTEM = (
    "You analyze conversation transcripts and extract a structured record. "
    "Be faithful to the transcript and do not invent facts.\n"
    "- participants: the distinct people involved; use real names when known, "
    "otherwise the speaker labels.\n"
    "- topics: 3-8 short noun-phrase themes that were discussed.\n"
    "- decisions: concrete decisions reached, if any.\n"
    "- commitments: things a specific person agreed to do. `owner` must be one of "
    "the participants. `status` is 'open' unless the transcript shows it is "
    "already done. `due` is a stated date or timeframe, else null.\n"
    "- action_items: short imperative to-dos.\n"
    "- notable_quotes: a few memorable or important verbatim lines with speaker.\n"
    "- title: a short descriptive title. summary: 2-4 sentences. "
    "date: an ISO date if one is stated in the transcript, else null."
)


class InsightExtractor(Protocol):
    async def extract(self, transcript: Transcript) -> Insights: ...


class OpenAIInsightExtractor:
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o"):
        self._client = client
        self._model = model

    async def extract(self, transcript: Transcript) -> Insights:
        completion = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Transcript:\n\n{transcript.as_dialogue()}"},
            ],
            response_format=Insights,
        )
        return completion.choices[0].message.parsed
