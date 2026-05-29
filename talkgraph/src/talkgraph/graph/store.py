from __future__ import annotations

import json
from typing import Optional

from neo4j import AsyncGraphDatabase

from ..models import Insights, Transcript


def normalize_name(name: str) -> str:
    """Key used to merge the same person/topic across conversations."""
    return " ".join(name.strip().lower().split())


_CONSTRAINTS = [
    "CREATE CONSTRAINT person_key IF NOT EXISTS FOR (p:Person) REQUIRE p.key IS UNIQUE",
    "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT topic_key IF NOT EXISTS FOR (t:Topic) REQUIRE t.key IS UNIQUE",
]

# Entity resolution happens here: people and topics are MERGEd by normalized key,
# so a new conversation links into the existing graph instead of duplicating nodes.
_INGEST = """
MERGE (c:Conversation {id: $id})
SET c.title=$title, c.summary=$summary, c.date=$date, c.source=$source,
    c.transcript=$transcript, c.audio_path=$audio_path, c.duration=$duration,
    c.action_items=$action_items, c.notable_quotes=$notable_quotes
WITH c
CALL (c) {
  UNWIND $participants AS p
  MERGE (person:Person {key: p.key}) ON CREATE SET person.name = p.name
  MERGE (person)-[:PARTICIPATED_IN]->(c)
}
CALL (c) {
  UNWIND $topics AS t
  MERGE (topic:Topic {key: t.key}) ON CREATE SET topic.name = t.name
  MERGE (c)-[:ABOUT]->(topic)
}
CALL (c) {
  UNWIND $decisions AS dtext
  CREATE (d:Decision {text: dtext, conversation_id: c.id})
  MERGE (c)-[:REACHED]->(d)
}
CALL (c) {
  UNWIND $commitments AS cm
  MERGE (owner:Person {key: cm.owner_key}) ON CREATE SET owner.name = cm.owner_name
  CREATE (m:Commitment {text: cm.text, status: cm.status, due: cm.due, conversation_id: c.id})
  MERGE (owner)-[:MADE]->(m)
  MERGE (m)-[:IN]->(c)
}
RETURN c.id AS id
"""

_PERSON_VIEW = """
MATCH (p:Person {key: $key})
RETURN p.name AS name,
  [(p)-[:PARTICIPATED_IN]->(c) | {id: c.id, title: c.title, date: c.date, summary: c.summary}] AS conversations,
  [(p)-[:PARTICIPATED_IN]->(:Conversation)-[:ABOUT]->(t) | t.name] AS topics,
  [(p)-[:MADE]->(m) | {text: m.text, status: m.status, due: m.due, conversation_id: m.conversation_id}] AS commitments,
  [(p)-[:PARTICIPATED_IN]->(:Conversation)<-[:PARTICIPATED_IN]-(o) WHERE o <> p | o.name] AS co_participants
"""

_CONVERSATION = """
MATCH (c:Conversation {id: $id})
RETURN c {.*} AS conversation,
  [(p)-[:PARTICIPATED_IN]->(c) | p.name] AS participants,
  [(c)-[:ABOUT]->(t) | t.name] AS topics,
  [(c)-[:REACHED]->(d) | d.text] AS decisions,
  [(o)-[:MADE]->(m)-[:IN]->(c) | {text: m.text, owner: o.name, status: m.status, due: m.due}] AS commitments
"""

_COMMITMENTS = """
MATCH (owner:Person)-[:MADE]->(m:Commitment)-[:IN]->(c:Conversation)
WHERE $status IS NULL OR m.status = $status
RETURN m.text AS text, m.status AS status, m.due AS due, owner.name AS owner,
       c.id AS conversation_id, c.title AS conversation_title
ORDER BY c.date DESC
"""

# Topic timeline: which conversations is a topic discussed in, by whom, when.
# Mirror of _PERSON_VIEW for the topic-centric axis.
_TOPIC_VIEW = """
MATCH (t:Topic {key: $key})
RETURN t.name AS name,
  [(c:Conversation)-[:ABOUT]->(t) | {id: c.id, title: c.title, date: c.date, summary: c.summary}] AS conversations,
  [(p:Person)-[:PARTICIPATED_IN]->(:Conversation)-[:ABOUT]->(t) | p.name] AS participants_raw
"""

# Per-person commitments. The WHERE inside the pattern comprehension applies at
# match time, so missing/filtered commitments produce an empty list (not the
# all-null artifact that an OPTIONAL MATCH + collect() would).
_PERSON_COMMITMENTS = """
MATCH (p:Person {key: $key})
RETURN p.name AS person,
  [(p)-[:MADE]->(m:Commitment)-[:IN]->(c:Conversation)
   WHERE $status IS NULL OR m.status = $status
   | {text: m.text, status: m.status, due: m.due,
      conversation_id: c.id, conversation_title: c.title, conversation_date: c.date}] AS commitments_raw
"""


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def verify(self) -> None:
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_constraints(self) -> None:
        async with self._driver.session() as session:
            for stmt in _CONSTRAINTS:
                await session.run(stmt)

    async def ingest_conversation(
        self,
        *,
        conversation_id: str,
        insights: Insights,
        transcript: Transcript,
        audio_path: Optional[str] = None,
        source: str = "upload",
        date: Optional[str] = None,
    ) -> None:
        participants = [
            {"key": normalize_name(p), "name": p} for p in dict.fromkeys(insights.participants)
        ]
        topics = [{"key": normalize_name(t), "name": t} for t in dict.fromkeys(insights.topics)]
        commitments = [
            {
                "text": c.text,
                "owner_key": normalize_name(c.owner),
                "owner_name": c.owner,
                "status": c.status,
                "due": c.due,
            }
            for c in insights.commitments
        ]
        params = {
            "id": conversation_id,
            "title": insights.title,
            "summary": insights.summary,
            "date": date or insights.date,
            "source": source,
            "transcript": transcript.as_dialogue(),
            "audio_path": audio_path,
            "duration": transcript.duration,
            "action_items": insights.action_items,
            "notable_quotes": json.dumps([q.model_dump() for q in insights.notable_quotes]),
            "participants": participants,
            "topics": topics,
            "decisions": insights.decisions,
            "commitments": commitments,
        }
        async with self._driver.session() as session:
            await session.run(_INGEST, params)

    async def get_person_view(self, name: str) -> Optional[dict]:
        async with self._driver.session() as session:
            result = await session.run(_PERSON_VIEW, {"key": normalize_name(name)})
            record = await result.single()
        if record is None:
            return None
        data = record.data()
        data["topics"] = sorted(set(data["topics"]))
        data["co_participants"] = sorted(set(data["co_participants"]))
        return data

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        async with self._driver.session() as session:
            result = await session.run(_CONVERSATION, {"id": conversation_id})
            record = await result.single()
        if record is None:
            return None
        data = record.data()
        conv = data.get("conversation") or {}
        if conv.get("notable_quotes"):
            try:
                conv["notable_quotes"] = json.loads(conv["notable_quotes"])
            except (ValueError, TypeError):
                pass
        data["conversation"] = conv
        return data

    async def get_commitments(self, status: Optional[str] = None) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(_COMMITMENTS, {"status": status})
            return [record.data() async for record in result]

    async def get_topic_view(self, name: str) -> Optional[dict]:
        """Topic-centric view: conversations the topic appears in + who's discussed it.

        Conversations are sorted by date desc (None last). Participants are aggregated
        across conversations with a per-person `conversation_count`, sorted by count
        desc then name asc.
        """
        async with self._driver.session() as session:
            result = await session.run(_TOPIC_VIEW, {"key": normalize_name(name)})
            record = await result.single()
        if record is None:
            return None
        data = record.data()
        # date desc, None last; id is the stable tiebreak so undated conversations
        # don't reshuffle between calls.
        dated = [c for c in (data.get("conversations") or []) if c.get("date")]
        undated = [c for c in (data.get("conversations") or []) if not c.get("date")]
        dated.sort(key=lambda c: (c["date"], c.get("id") or ""), reverse=True)
        undated.sort(key=lambda c: c.get("id") or "")
        data["conversations"] = dated + undated

        counts: dict[str, int] = {}
        for n in data.pop("participants_raw", []) or []:
            counts[n] = counts.get(n, 0) + 1
        data["participants"] = [
            {"name": n, "conversation_count": c}
            for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return data

    async def get_person_commitments(
        self, name: str, status: Optional[str] = None
    ) -> Optional[list[dict]]:
        """Commitments owned by the named person, optionally filtered by status.

        Returns None when the person does not exist (→ 404), an empty list when
        they exist but have no matching commitments. Sorted by conversation date
        desc, with None last.
        """
        async with self._driver.session() as session:
            result = await session.run(
                _PERSON_COMMITMENTS, {"key": normalize_name(name), "status": status}
            )
            record = await result.single()
        if record is None:
            return None
        commitments = record.data().get("commitments_raw") or []
        dated = [c for c in commitments if c.get("conversation_date")]
        undated = [c for c in commitments if not c.get("conversation_date")]
        dated.sort(
            key=lambda c: (c["conversation_date"], c.get("conversation_id") or ""),
            reverse=True,
        )
        undated.sort(key=lambda c: c.get("conversation_id") or "")
        return dated + undated
