"""Topic index + related topics: reach ordering, participant dedup,
limit pass-through, and co-occurrence aggregation.
"""

from _fakes import FakeRecord, FakeResult, store_with_fake


async def test_list_topics_dedupes_participants_and_passes_limit():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        rows=[
            FakeRecord(
                {
                    "name": "remote work",
                    "conversation_count": 3,
                    # Alice appears in two of three conversations → 2 entries.
                    "participant_names": ["Alice", "Alice", "Bob", "Carol"],
                }
            ),
            FakeRecord(
                {
                    "name": "commute",
                    "conversation_count": 1,
                    "participant_names": ["Alice", "Bob"],
                }
            ),
        ]
    )

    topics = await store.list_topics(limit=10)

    _query, params = fake.calls[0]
    assert params == {"limit": 10}
    # participant_count is unique people, not raw matches
    assert topics == [
        {"name": "remote work", "conversation_count": 3, "participant_count": 3},
        {"name": "commute", "conversation_count": 1, "participant_count": 2},
    ]


async def test_list_topics_empty_graph_returns_empty_list():
    store, _ = store_with_fake()
    # default FakeResult yields no rows
    assert await store.list_topics() == []


async def test_get_related_topics_counts_co_occurrence_and_sorts():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "name": "remote work",
                # "commute" co-occurs in 2 conversations, "home office" in 1.
                "related_raw": ["commute", "home office", "commute", "equipment"],
            }
        )
    )

    related = await store.get_related_topics("Remote Work")

    _query, params = fake.calls[0]
    assert params["key"] == "remote work"
    # sorted by co_occurrence desc, then name asc for ties
    assert related == [
        {"name": "commute", "co_occurrence": 2},
        {"name": "equipment", "co_occurrence": 1},
        {"name": "home office", "co_occurrence": 1},
    ]


async def test_get_related_topics_missing_returns_none():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(record=None)
    assert await store.get_related_topics("ghost-topic") is None


async def test_get_related_topics_isolated_topic_returns_empty_list():
    """Topic exists but has never co-occurred with another → empty, not None."""
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord({"name": "lonely", "related_raw": []})
    )
    assert await store.get_related_topics("lonely") == []


async def test_get_related_topics_respects_limit():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "name": "t",
                "related_raw": ["a", "b", "c", "d", "e"],
            }
        )
    )
    related = await store.get_related_topics("t", limit=2)
    assert [r["name"] for r in related] == ["a", "b"]
