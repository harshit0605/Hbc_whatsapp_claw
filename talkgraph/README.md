# talkgraph

Capture the conversations worth keeping. Transcribe them, figure out who said
what, extract the structured insights (decisions, commitments, topics,
quotes), and ingest into a **knowledge graph that compounds across
conversations** — so "what has Alice and I talked about" or "who's been
discussing remote work, when" becomes a real query.

Pipeline:

```
ingest → transcribe → diarize → extract → graph-merge → query
```

Each stage sits behind a swappable `Protocol`. The graph stores `Person`,
`Conversation`, `Topic`, `Commitment`, `Decision` nodes in Neo4j, MERGE-ing
people and topics by a normalized key so each new conversation links into
the existing graph instead of duplicating nodes.

For the full design history see [`CONTINUATION.md`](CONTINUATION.md); for the
live-WhatsApp-wire roadmap see [`PHASE_D_PLAN.md`](PHASE_D_PLAN.md).

---

## Quickstart (5 minutes)

```bash
cp .env.example .env             # OPENAI_API_KEY only needed for real audio
docker compose up -d             # local Neo4j: bolt :7687, browser :7474
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                 # expect: 46 passed, 7 skipped
```

Load the two example fixtures (no OPENAI_API_KEY needed — they're
pre-extracted), then see the compounding graph view:

```bash
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_a.json
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_b.json
.venv/bin/python scripts/show_graph.py
```

`show_graph.py` prints the topic index, the timeline for "remote work" (which
bridges both fixtures), Alice's open commitments across both conversations,
and dyad views of Alice∩Bob and Alice∩Carol — the magic moment.

You can also poke around visually at <http://localhost:7474> (login
`neo4j` / `talkgraph-dev`).

## Capture a real voice note

The first thing that drives the real Whisper + GPT-4o path end-to-end is
the WhatsApp bootstrap:

```bash
# needs a real OPENAI_API_KEY in .env
.venv/bin/python scripts/ingest_voice_note.py path/to/voice.opus

# or a folder of exports
.venv/bin/python scripts/ingest_voice_note.py --dir ~/Downloads/whatsapp_exports/

# or watch a folder for new files
.venv/bin/python scripts/ingest_voice_note.py --watch ~/Downloads/whatsapp_exports/
```

For the *live* WhatsApp wire (OpenCLAW plugin), see `PHASE_D_PLAN.md`.

## API surface

Run with `.venv/bin/uvicorn talkgraph.main:app --reload`. Auto-generated
docs at <http://localhost:8000/docs>.

| Method | Path | Returns |
|---|---|---|
| `GET`  | `/health` | `{"status": "ok"}` — liveness probe, no deps checked |
| `GET`  | `/healthz` | `{"status": "ready"}` (200) / `{"detail": "neo4j unreachable: …"}` (503) — readiness probe with Neo4j ping |
| `POST` | `/conversations` | Upload an audio file; runs the full pipeline; returns `{conversation_id, insights}` |
| `GET`  | `/conversations/{id}` | Conversation + participants + topics + decisions + commitments |
| `GET`  | `/people/{name}` | Person view: conversations, merged topics, open commitments, co-participants |
| `GET`  | `/people/{name}/commitments?status=open` | Just the commitments this person owes |
| `GET`  | `/people/{a}/with/{b}` | Dyad view: every conversation A and B shared, with topics + decisions + commitments per conversation |
| `GET`  | `/topics` | All topics ranked by reach (conversation_count desc, unique participant_count) |
| `GET`  | `/topics/{name}` | Topic timeline: conversations + per-participant counts |
| `GET`  | `/topics/{name}/related` | Topics that co-occur with this one in shared conversations |
| `GET`  | `/commitments?status=open` | All commitments globally, optionally filtered by status |

**Auth:** when `API_TOKEN` is set in `.env`, every route except `/health` and
`/healthz` requires `Authorization: Bearer <API_TOKEN>`. Empty token = dev
mode, no auth.

## Project layout

```
talkgraph/
  pyproject.toml          # Python ≥3.10; deps: fastapi, openai, neo4j, pydantic(-settings)
  docker-compose.yml      # Neo4j 5
  .env.example            # OPENAI_API_KEY, NEO4J_*, API_TOKEN, LOG_LEVEL, DATA_DIR
  src/talkgraph/
    main.py               # FastAPI app + lifespan
    settings.py           # pydantic-settings
    models.py             # incl. OpenAI structured-output schemas
    _logging.py           # setup_logging()
    api/
      auth.py             # Bearer-token dependency
      routes.py           # all REST endpoints
    pipeline/
      transcribe.py       # OpenAI Whisper
      diarize.py          # LLM-based speaker attribution (swappable)
      extract.py          # GPT-4o structured-output insight extraction
      orchestrator.py     # runs the stages end-to-end
    graph/
      store.py            # Neo4jGraphStore: ingest + all queries
  scripts/
    run_sample.py         # one-shot pipeline run on --audio or --transcript
    show_graph.py         # human-readable demo view of the new query surface
    ingest_voice_note.py  # batch/watch capture for WhatsApp exports
  tests/                  # 46 hermetic + 7 integration (opt-in)
  examples/               # two pre-extracted fixtures used by tests + demo
```

## Testing

```bash
.venv/bin/pytest                                            # 46 hermetic
TALKGRAPH_NEO4J_INTEGRATION=1 .venv/bin/pytest              # +7 integration
```

The integration suite wipes the graph, ingests both example fixtures via the
real ingest path, then asserts the full query surface (person view, topic
view, dyad view, person commitments, topic index, related topics). Skipped
by default to keep `pytest` hermetic.

## Status

| | Status |
|---|---|
| Pipeline runs offline on fixtures | ✅ |
| Live Neo4j ingest end-to-end | ✅ verified |
| Person / topic / dyad / commitments query surface | ✅ |
| WhatsApp file-forwarding capture | ✅ (Phase C) |
| Real-audio Whisper + GPT-4o path | ⚠️ tool ships in `ingest_voice_note.py`; first real file will tell us if it holds up |
| Live WhatsApp via OpenCLAW plugin | 📄 planned in `PHASE_D_PLAN.md`, not built |
| Sharper acoustic diarization (pyannote / AssemblyAI) | 📄 open |
| Multi-user graph partitioning, consent UX | 📄 spawned arch task |
