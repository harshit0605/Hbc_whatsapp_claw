"""Topic-centric view: key normalization, date-desc conversation sort, and
per-participant `conversation_count` aggregation across the topic's conversations.

Uses the same fake driver pattern as test_graph_ingest to stay hermetic.
"""

from _fakes import FakeRecord, FakeResult, store_with_fake


async def test_topic_view_normalizes_key_and_aggregates_participants():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "name": "remote work",
                # Two conversations about "remote work"; Alice in both, Bob & Carol in one each.
                "conversations": [
                    {"id": "c1", "title": "first", "date": "2026-05-10", "summary": "s1"},
                    {"id": "c2", "title": "second", "date": "2026-05-24", "summary": "s2"},
                ],
                # raw participants list: one entry per (person, conversation-on-topic) match
                "participants_raw": ["Alice", "Bob", "Alice", "Carol"],
            }
        )
    )

    view = await store.get_topic_view("  Remote Work ")

    # key was normalized before hitting Cypher
    _query, params = fake.calls[0]
    assert params["key"] == "remote work"

    # date desc
    assert [c["id"] for c in view["conversations"]] == ["c2", "c1"]

    # per-person count, sorted by count desc then name asc
    assert view["participants"] == [
        {"name": "Alice", "conversation_count": 2},
        {"name": "Bob", "conversation_count": 1},
        {"name": "Carol", "conversation_count": 1},
    ]


async def test_topic_view_returns_none_when_missing():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(record=None)

    assert await store.get_topic_view("never-mentioned") is None


async def test_topic_view_handles_undated_conversations_last():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "name": "remote work",
                "conversations": [
                    {"id": "c-undated", "title": "u", "date": None, "summary": "s"},
                    {"id": "c-old", "title": "o", "date": "2026-01-01", "summary": "s"},
                    {"id": "c-new", "title": "n", "date": "2026-12-31", "summary": "s"},
                ],
                "participants_raw": [],
            }
        )
    )

    view = await store.get_topic_view("remote work")
    # dated descending, undated at the end
    assert [c["id"] for c in view["conversations"]] == ["c-new", "c-old", "c-undated"]
    assert view["participants"] == []
