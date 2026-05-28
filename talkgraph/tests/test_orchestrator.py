from talkgraph.models import Insights, Transcript, TranscriptSegment
from talkgraph.pipeline.orchestrator import Orchestrator


class FakeSTT:
    async def transcribe(self, audio_path):
        return Transcript(full_text="hi there", segments=[TranscriptSegment(text="hi there")])


class FakeDiarizer:
    async def diarize(self, transcript):
        return Transcript(
            full_text=transcript.full_text,
            segments=[
                TranscriptSegment(text=s.text, speaker="Speaker 1") for s in transcript.segments
            ],
        )


def _insights(title="t"):
    return Insights(
        title=title,
        summary="s",
        date=None,
        participants=["Alice"],
        topics=["x"],
        decisions=[],
        commitments=[],
        action_items=[],
        notable_quotes=[],
    )


class FakeExtractor:
    async def extract(self, transcript):
        return _insights()


class FakeGraph:
    def __init__(self):
        self.calls = []

    async def ingest_conversation(self, **kwargs):
        self.calls.append(kwargs)


async def test_process_audio_runs_full_pipeline():
    graph = FakeGraph()
    orch = Orchestrator(FakeSTT(), FakeDiarizer(), FakeExtractor(), graph)

    result = await orch.process_audio("x.wav")

    assert result.conversation_id
    assert result.insights.participants == ["Alice"]
    assert result.transcript.speaker_labeled()
    assert len(graph.calls) == 1
    assert graph.calls[0]["insights"].title == "t"


async def test_process_transcript_with_insights_skips_extractor():
    graph = FakeGraph()

    class BoomExtractor:
        async def extract(self, transcript):
            raise AssertionError("extractor should not be called when insights are provided")

    orch = Orchestrator(FakeSTT(), FakeDiarizer(), BoomExtractor(), graph)
    transcript = Transcript(
        full_text="a", segments=[TranscriptSegment(text="a", speaker="Alice")]
    )
    provided = _insights(title="provided")

    result = await orch.process_transcript(transcript, insights=provided)

    assert result.insights is provided
    assert graph.calls[0]["insights"] is provided


async def test_process_transcript_diarizes_when_unlabeled():
    graph = FakeGraph()
    orch = Orchestrator(FakeSTT(), FakeDiarizer(), FakeExtractor(), graph)
    transcript = Transcript(full_text="a", segments=[TranscriptSegment(text="a")])

    result = await orch.process_transcript(transcript)

    assert result.transcript.speaker_labeled()
