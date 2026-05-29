"""End-to-end integration: ingest both fixtures into a real Neo4j and exercise
every query the API exposes.

Opt-in to keep `pytest` hermetic by default. To run:
    docker compose up -d        # in talkgraph/
    TALKGRAPH_NEO4J_INTEGRATION=1 .venv/bin/pytest tests/test_graph_integration.py -v

The fixture wipes the graph at start, ingests both example transcripts, then
each test queries the resulting graph. State persists in the Neo4j volume so
you can also poke around at http://localhost:7474 after the run.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from talkgraph.graph.store import Neo4jGraphStore
from talkgraph.models import Insights, Transcript
from talkgraph.settings import get_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TALKGRAPH_NEO4J_INTEGRATION") != "1",
    reason="opt-in; set TALKGRAPH_NEO4J_INTEGRATION=1 with a running Neo4j to enable",
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load_fixture(path: Path) -> tuple[Transcript, Insights, str | None]:
    data = json.loads(path.read_text())
    segments = data.get("segments", [])
    full_text = data.get("full_text") or " ".join(s["text"] for s in segments)
    transcript = Transcript(
        full_text=full_text,
        segments=segments,
        language=data.get("language"),
        duration=data.get("duration"),
    )
    return transcript, Insights(**data["insights"]), data.get("date")


@pytest.fixture
async def graph():
    s = get_settings()
    g = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    await g.verify()
    # Reaching into ._driver is mildly tacky but this is the integration test —
    # we'd rather keep a destructive wipe_all() off the public surface.
    async with g._driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await g.ensure_constraints()
    for name in ("conversation_a.json", "conversation_b.json"):
        transcript, insights, date = _load_fixture(EXAMPLES / name)
        await g.ingest_conversation(
            conversation_id=str(uuid.uuid4()),
            insights=insights,
            transcript=transcript,
            date=date,
        )
    yield g
    await g.close()


async def test_alice_merges_across_both_fixtures(graph):
    view = await graph.get_person_view("Alice")
    assert view is not None
    assert len(view["conversations"]) == 2
    assert view["co_participants"] == ["Bob", "Carol"]
    # "remote work" appears in both fixtures; MERGE on key should keep one entry.
    assert view["topics"].count("remote work") == 1


async def test_remote_work_topic_bridges_both_conversations(graph):
    view = await graph.get_topic_view("remote work")
    assert view is not None
    assert len(view["conversations"]) == 2
    by_name = {p["name"]: p["conversation_count"] for p in view["participants"]}
    assert by_name == {"Alice": 2, "Bob": 1, "Carol": 1}


async def test_dyad_views_partition_correctly(graph):
    alice_bob = await graph.get_dyad_view("Alice", "Bob")
    alice_carol = await graph.get_dyad_view("Alice", "Carol")
    bob_carol = await graph.get_dyad_view("Bob", "Carol")
    assert len(alice_bob["conversations"]) == 1
    assert len(alice_carol["conversations"]) == 1
    # Bob and Carol both exist but never shared a conversation.
    assert bob_carol == {"a": "Bob", "b": "Carol", "conversations": []}


async def test_dyad_view_missing_person_returns_none(graph):
    assert await graph.get_dyad_view("Alice", "Ghost") is None


async def test_topic_index_ranks_remote_work_first(graph):
    topics = await graph.list_topics()
    assert topics[0]["name"] == "remote work"
    assert topics[0]["conversation_count"] == 2
    assert topics[0]["participant_count"] == 3  # Alice, Bob, Carol


async def test_related_to_remote_work_excludes_self_and_lists_neighbours(graph):
    related = await graph.get_related_topics("remote work")
    names = {r["name"] for r in related}
    assert "remote work" not in names
    assert names == {"apartment move", "commute", "equipment", "home office"}


async def test_alice_open_commitments_span_both_conversations(graph):
    commitments = await graph.get_person_commitments("Alice", status="open")
    assert commitments is not None
    assert len(commitments) == 2
    texts = {c["text"] for c in commitments}
    assert texts == {
        "Draft a remote-work proposal",
        "Research monitors for the home office",
    }
