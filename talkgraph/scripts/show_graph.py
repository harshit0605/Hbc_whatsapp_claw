"""Print the compounding-graph queries in a human-readable form.

Run AFTER ingesting at least one conversation (e.g. via run_sample.py).

    python scripts/show_graph.py
    python scripts/show_graph.py --topic "remote work" --person Alice --partners Bob,Carol

Hits the graph directly — no OpenAI calls, no API server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import textwrap

from talkgraph.graph.store import Neo4jGraphStore
from talkgraph.settings import get_settings

_BAR = "=" * 78


def _section(title: str) -> None:
    print(f"\n{_BAR}\n{title}\n{_BAR}")


def _print_topic_index(topics: list[dict]) -> None:
    _section("TOPIC INDEX  (reach across all conversations)")
    if not topics:
        print("  (no topics yet — ingest a conversation first)")
        return
    width = max(len(t["name"]) for t in topics)
    for t in topics:
        print(
            f"  {t['name']:<{width}}  "
            f"{t['conversation_count']:>2} conversation(s)  "
            f"{t['participant_count']:>2} distinct people"
        )


def _print_topic_view(topic: str, view: dict | None) -> None:
    _section(f"TOPIC TIMELINE  ·  {topic!r}")
    if view is None:
        print(f"  (topic {topic!r} not in graph)")
        return
    if not view["conversations"]:
        print("  (no conversations on this topic yet)")
    for c in view["conversations"]:
        print(f"  • {c.get('date') or '????-??-??'}  —  {c['title']}")
        if c.get("summary"):
            print(textwrap.fill(c["summary"], width=76, initial_indent="      ", subsequent_indent="      "))
    if view["participants"]:
        print("\n  Discussed by:")
        for p in view["participants"]:
            print(f"    - {p['name']}  ({p['conversation_count']} conv)")


def _print_related(topic: str, related: list[dict] | None) -> None:
    _section(f"CO-OCCURRING TOPICS  ·  {topic!r}")
    if related is None:
        print(f"  (topic {topic!r} not in graph)")
        return
    if not related:
        print("  (never discussed alongside another topic)")
        return
    width = max(len(r["name"]) for r in related)
    for r in related:
        print(f"  {r['name']:<{width}}  · co-occurrence {r['co_occurrence']}")


def _print_person_commitments(person: str, commitments: list[dict] | None) -> None:
    _section(f"OPEN COMMITMENTS  ·  {person}")
    if commitments is None:
        print(f"  (person {person!r} not in graph)")
        return
    if not commitments:
        print("  (no open commitments)")
        return
    for c in commitments:
        due = f" (due {c['due']})" if c.get("due") else ""
        print(f"  • {c['text']}{due}")
        print(f"      from: {c.get('conversation_title')}  [{c.get('conversation_date') or '????'}]")


def _print_dyad(a: str, b: str, view: dict | None) -> None:
    _section(f"WHAT  {a}  AND  {b}  DISCUSSED")
    if view is None:
        print(f"  (at least one of {a!r}, {b!r} is not in the graph)")
        return
    convs = view["conversations"]
    if not convs:
        print(f"  (no shared conversations between {a} and {b} yet)")
        return
    for c in convs:
        print(f"\n  • {c.get('date') or '????-??-??'}  —  {c['title']}")
        if c.get("topics"):
            print(f"      topics:     {', '.join(c['topics'])}")
        if c.get("decisions"):
            for d in c["decisions"]:
                print(f"      decision:   {d}")
        if c.get("commitments"):
            for cm in c["commitments"]:
                due = f" (due {cm['due']})" if cm.get("due") else ""
                print(f"      commitment: {cm['owner']} → {cm['text']}{due}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="remote work", help="topic to focus on")
    parser.add_argument("--person", default="Alice", help="person to focus on")
    parser.add_argument(
        "--partners",
        default="Bob,Carol",
        help="comma-separated names; one dyad section per partner against --person",
    )
    parser.add_argument(
        "--raw", action="store_true", help="dump JSON instead of formatted output"
    )
    args = parser.parse_args()

    settings = get_settings()
    graph = Neo4jGraphStore(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
    )
    await graph.verify()

    topics = await graph.list_topics()
    topic_view = await graph.get_topic_view(args.topic)
    related = await graph.get_related_topics(args.topic)
    commitments = await graph.get_person_commitments(args.person, status="open")
    partners = [p.strip() for p in args.partners.split(",") if p.strip()]
    dyads = {p: await graph.get_dyad_view(args.person, p) for p in partners}

    if args.raw:
        print(
            json.dumps(
                {
                    "topic_index": topics,
                    f"topic:{args.topic}": topic_view,
                    f"related:{args.topic}": related,
                    f"{args.person}_open_commitments": commitments,
                    "dyads": {f"{args.person}∩{p}": v for p, v in dyads.items()},
                },
                indent=2,
                default=str,
            )
        )
    else:
        _print_topic_index(topics)
        _print_topic_view(args.topic, topic_view)
        _print_related(args.topic, related)
        _print_person_commitments(args.person, commitments)
        for partner, view in dyads.items():
            _print_dyad(args.person, partner, view)

    await graph.close()


if __name__ == "__main__":
    asyncio.run(main())
