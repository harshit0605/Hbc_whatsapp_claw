from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Protocol

from ..models import ConversationResult, Insights, Transcript
from .diarize import Diarizer
from .extract import InsightExtractor
from .transcribe import STTProvider


class GraphStore(Protocol):
    async def ingest_conversation(
        self,
        *,
        conversation_id: str,
        insights: Insights,
        transcript: Transcript,
        audio_path: Optional[str],
        source: str,
        date: Optional[str],
    ) -> None: ...


@dataclass
class Orchestrator:
    """Runs ingest -> transcribe -> diarize -> extract -> graph-merge."""

    stt: STTProvider
    diarizer: Diarizer
    extractor: InsightExtractor
    graph: GraphStore

    async def process_audio(
        self, audio_path: str, source: str = "upload", date: Optional[str] = None
    ) -> ConversationResult:
        transcript = await self.stt.transcribe(audio_path)
        transcript = await self.diarizer.diarize(transcript)
        return await self._finish(transcript, audio_path=audio_path, source=source, date=date)

    async def process_transcript(
        self,
        transcript: Transcript,
        source: str = "transcript",
        date: Optional[str] = None,
        audio_path: Optional[str] = None,
        insights: Optional[Insights] = None,
    ) -> ConversationResult:
        if not transcript.speaker_labeled():
            transcript = await self.diarizer.diarize(transcript)
        return await self._finish(
            transcript, audio_path=audio_path, source=source, date=date, insights=insights
        )

    async def _finish(
        self,
        transcript: Transcript,
        *,
        audio_path: Optional[str],
        source: str,
        date: Optional[str],
        insights: Optional[Insights] = None,
    ) -> ConversationResult:
        if insights is None:
            insights = await self.extractor.extract(transcript)
        conversation_id = str(uuid.uuid4())
        await self.graph.ingest_conversation(
            conversation_id=conversation_id,
            insights=insights,
            transcript=transcript,
            audio_path=audio_path,
            source=source,
            date=date,
        )
        return ConversationResult(
            conversation_id=conversation_id, insights=insights, transcript=transcript
        )
