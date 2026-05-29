"""Per-person commitments query: key normalization, status pass-through,
missing-person → None, conversation-date sort.
"""

from _fakes import FakeRecord, FakeResult, store_with_fake


async def test_person_commitments_normalizes_key_and_passes_status():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "person": "Alice",
                "commitments_raw": [
                    {
                        "text": "Draft proposal",
                        "status": "open",
                        "due": "Friday",
                        "conversation_id": "c-old",
                        "conversation_title": "first",
                        "conversation_date": "2026-05-10",
                    },
                    {
                        "text": "Research monitors",
                        "status": "open",
                        "due": "weekend",
                        "conversation_id": "c-new",
                        "conversation_title": "second",
                        "conversation_date": "2026-05-24",
                    },
                ],
            }
        )
    )

    commitments = await store.get_person_commitments("  ALICE ", status="open")

    _query, params = fake.calls[0]
    assert params == {"key": "alice", "status": "open"}
    # sorted by conversation_date desc
    assert [c["conversation_id"] for c in commitments] == ["c-new", "c-old"]


async def test_person_commitments_missing_person_returns_none():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(record=None)

    assert await store.get_person_commitments("ghost") is None


async def test_person_commitments_empty_when_no_commitments():
    """Person exists but has nothing matching the filter → empty list, not 404."""
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord({"person": "Alice", "commitments_raw": []})
    )

    assert await store.get_person_commitments("Alice", status="done") == []


async def test_person_commitments_status_none_passes_through():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord({"person": "Alice", "commitments_raw": []})
    )

    await store.get_person_commitments("Alice", status=None)
    _query, params = fake.calls[0]
    assert params["status"] is None
