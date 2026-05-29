"""Dyad view (what did A and B discuss together): key normalization for both
sides, conversation date-desc sort, a==b ValueError, missing-person None,
empty-but-valid case returns dict-with-empty-list rather than None.
"""

import pytest

from _fakes import FakeRecord, FakeResult, store_with_fake


async def test_dyad_view_normalizes_both_keys_and_sorts_by_date():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "a": "Alice",
                "b": "Bob",
                "conversations_raw": [
                    {
                        "id": "c-old",
                        "title": "first",
                        "date": "2026-01-01",
                        "summary": "s1",
                        "topics": ["t"],
                        "decisions": [],
                        "commitments": [],
                    },
                    {
                        "id": "c-new",
                        "title": "second",
                        "date": "2026-12-31",
                        "summary": "s2",
                        "topics": ["t"],
                        "decisions": [],
                        "commitments": [],
                    },
                ],
            }
        )
    )

    view = await store.get_dyad_view("  ALICE", " bob ")

    _query, params = fake.calls[0]
    assert params == {"a_key": "alice", "b_key": "bob"}
    assert [c["id"] for c in view["conversations"]] == ["c-new", "c-old"]
    assert view["a"] == "Alice" and view["b"] == "Bob"


async def test_dyad_view_same_person_raises():
    store, _ = store_with_fake()
    with pytest.raises(ValueError):
        await store.get_dyad_view("Alice", "  alice ")


async def test_dyad_view_missing_person_returns_none():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(record=None)
    assert await store.get_dyad_view("Alice", "Ghost") is None


async def test_dyad_view_no_shared_conversations_returns_empty_list():
    """Both people exist but have never spoken together — distinct from 404."""
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord({"a": "Alice", "b": "Carol", "conversations_raw": []})
    )

    view = await store.get_dyad_view("Alice", "Carol")
    assert view == {"a": "Alice", "b": "Carol", "conversations": []}


async def test_dyad_view_undated_conversations_last():
    store, fake = store_with_fake()
    fake.next_result = FakeResult(
        record=FakeRecord(
            {
                "a": "Alice",
                "b": "Bob",
                "conversations_raw": [
                    {"id": "c-u", "title": "u", "date": None, "summary": "s",
                     "topics": [], "decisions": [], "commitments": []},
                    {"id": "c-d", "title": "d", "date": "2026-05-10", "summary": "s",
                     "topics": [], "decisions": [], "commitments": []},
                ],
            }
        )
    )

    view = await store.get_dyad_view("Alice", "Bob")
    assert [c["id"] for c in view["conversations"]] == ["c-d", "c-u"]
