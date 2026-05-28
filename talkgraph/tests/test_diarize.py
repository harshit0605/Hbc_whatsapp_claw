from talkgraph.models import (
    DiarizationResult,
    SpeakerAssignment,
    SpeakerName,
    Transcript,
    TranscriptSegment,
)
from talkgraph.pipeline.diarize import _apply


def test_apply_assigns_names_and_numbered_labels():
    segments = [
        TranscriptSegment(text="hello"),
        TranscriptSegment(text="hi there"),
        TranscriptSegment(text="bye"),
    ]
    result = DiarizationResult(
        assignments=[
            SpeakerAssignment(index=0, speaker_id="S1"),
            SpeakerAssignment(index=1, speaker_id="S2"),
            SpeakerAssignment(index=2, speaker_id="S1"),
        ],
        names=[SpeakerName(speaker_id="S2", name="Alice")],
    )
    transcript = Transcript(full_text="hello hi there bye", segments=segments)

    out = _apply(segments, result, transcript)

    assert [s.speaker for s in out.segments] == ["Speaker 1", "Alice", "Speaker 1"]
    assert out.speaker_labeled()
