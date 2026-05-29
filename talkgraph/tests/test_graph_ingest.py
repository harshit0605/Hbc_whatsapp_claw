"""Validate graph ingest param-building / entity-resolution keying offline.

A live Neo4j would also validate the Cypher itself; here we inject a fake async
driver to assert the parameters (normalized keys, dedup, JSON serialization) that
the MERGE query receives.
"""

import json

from talkgraph.models import (
    Commitment,
    Insights,
    Quote,
    Transcript,
    TranscriptSegment,
)

from _fakes import FakeRecord, FakeResult, store_with_fake


async def test_ingest_builds_normalized_params():
    store, fake = store_with_fake()
    insights = Insights(
        title="T",
        summary="S",
        date="2026-05-10",
        participants=["Alice", "Bob", "Alice"],
        topics=["Remote Work"],
        decisions=["ship it"],
        commitments=[Commitment(text="draft", owner="Alice", due="Friday", status="open")],
        action_items=["do x"],
        notable_quotes=[Quote(speaker="Alice", quote="hello")],
    )
    transcript = Transcript(
        full_text="hi", segments=[TranscriptSegment(text="hi", speaker="Alice")]
    )

    await store.ingest_conversation(
        conversation_id="c1",
        insights=insights,
        transcript=transcript,
        audio_path="/a.wav",
        source="upload",
        date=None,
    )

    _query, params = fake.calls[0]
    assert params["id"] == "c1"
    # de-duplicated, normalized keys with original display names
    assert params["participants"] == [
        {"key": "alice", "name": "Alice"},
        {"key": "bob", "name": "Bob"},
    ]
    assert params["topics"] == [{"key": "remote work", "name": "Remote Work"}]
    assert params["commitments"][0]["owner_key"] == "alice"
    assert params["date"] == "2026-05-10"  # falls back to insights.date
    assert json.loads(params["notable_quotes"]) == [{"speaker": "Alice", "quote": "hello"}]


async def test_person_view_normalizes_key_and_dedupes():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "name": "Alice",
                "conversations": [{"id": "c1"}],
                "topics": ["remote work", "remote work", "commute"],
                "commitments": [],
                "co_participants": ["Bob", "Bob", "Carol"],
            }
        )
    )

    view = await store.get_person_view("  ALICE ")

    _query, params = fake.calls[0]
    assert params["key"] == "alice"
    assert view["topics"] == ["commute", "remote work"]
    assert view["co_participants"] == ["Bob", "Carol"]
