"""Validate graph ingest param-building / entity-resolution keying offline.

A live Neo4j would also validate the Cypher itself; here we inject a fake async
driver to assert the parameters (normalized keys, dedup, JSON serialization) that
the MERGE query receives.
"""

import json

from talkgraph.graph.store import Neo4jGraphStore
from talkgraph.models import (
    Commitment,
    Insights,
    Quote,
    Transcript,
    TranscriptSegment,
)


class FakeRecord:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeResult:
    def __init__(self, record=None, rows=None):
        self._record = record
        self._rows = list(rows or [])

    async def single(self):
        return self._record

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeSession:
    def __init__(self, driver):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, params=None):
        self._driver.calls.append((query, params))
        return self._driver.next_result


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.next_result = FakeResult()

    def session(self):
        return FakeSession(self)

    async def close(self):
        return None


def _store_with_fake():
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    fake = FakeDriver()
    store._driver = fake
    return store, fake


async def test_ingest_builds_normalized_params():
    store, fake = _store_with_fake()
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
    store, fake = _store_with_fake()
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
