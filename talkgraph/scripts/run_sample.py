"""Run the full pipeline on a local audio file or a transcript fixture.

Examples:
    # Real pipeline (needs OPENAI_API_KEY + Neo4j running):
    python scripts/run_sample.py --audio path/to/meeting.m4a

    # Offline graph demo (fixture already has speaker labels + insights):
    python scripts/run_sample.py --transcript examples/conversation_a.json
    python scripts/run_sample.py --transcript examples/conversation_b.json
    # then query people/Alice via the API or get_person_view.

Add --no-graph to skip Neo4j entirely (just print transcript + insights).
"""

from __future__ import annotations

import argparse
import asyncio
import json

from openai import AsyncOpenAI

from talkgraph.graph.store import Neo4jGraphStore
from talkgraph.models import Insights, Transcript
from talkgraph.pipeline.diarize import LLMDiarizer
from talkgraph.pipeline.extract import OpenAIInsightExtractor
from talkgraph.pipeline.orchestrator import Orchestrator
from talkgraph.pipeline.transcribe import OpenAISTTProvider
from talkgraph.settings import get_settings


class _NullGraph:
    async def ingest_conversation(self, **_):
        return None


def _load_transcript(path: str) -> tuple[Transcript, Insights | None, str | None]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    segments = data.get("segments", [])
    full_text = data.get("full_text") or " ".join(s["text"] for s in segments)
    transcript = Transcript(
        full_text=full_text,
        segments=segments,
        language=data.get("language"),
        duration=data.get("duration"),
    )
    insights = Insights(**data["insights"]) if data.get("insights") else None
    return transcript, insights, data.get("date")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio", help="path to an audio file")
    source.add_argument("--transcript", help="path to a transcript fixture (.json)")
    parser.add_argument("--no-graph", action="store_true", help="skip Neo4j ingest/queries")
    args = parser.parse_args()

    settings = get_settings()
    # Placeholder lets the fixture path (pre-labeled + pre-extracted) run fully
    # offline; any real STT/LLM call would still require a valid key.
    client = AsyncOpenAI(api_key=settings.openai_api_key or "offline-placeholder")

    if args.no_graph:
        graph = _NullGraph()
    else:
        graph = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        await graph.verify()
        await graph.ensure_constraints()

    orchestrator = Orchestrator(
        stt=OpenAISTTProvider(client, settings.openai_stt_model),
        diarizer=LLMDiarizer(client, settings.openai_diarize_model),
        extractor=OpenAIInsightExtractor(client, settings.openai_extract_model),
        graph=graph,
    )

    if args.audio:
        result = await orchestrator.process_audio(args.audio)
    else:
        transcript, insights, date = _load_transcript(args.transcript)
        result = await orchestrator.process_transcript(transcript, date=date, insights=insights)

    print("\n=== DIARIZED TRANSCRIPT ===")
    print(result.transcript.as_dialogue())
    print("\n=== INSIGHTS ===")
    print(result.insights.model_dump_json(indent=2))

    if not args.no_graph:
        for name in result.insights.participants:
            view = await graph.get_person_view(name)
            print(f"\n=== GRAPH VIEW: {name} ===")
            print(json.dumps(view, indent=2, default=str))
        await graph.close()

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
