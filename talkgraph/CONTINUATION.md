# talkgraph — Continuation Brief (complete context for a new thread)

> **How to use this doc:** paste it into a fresh Claude Code thread — ideally on
> your **local Mac**, where you have Docker and your OpenAI key — with the repo
> checked out (see §5). It is self-contained: an agent with zero prior context can
> continue from here. No `teleport` required.
>
> (If you *do* have `claude --teleport`, `HANDOFF.md` covers that path instead.)

---

## 1. The product idea

An app for capturing the conversations worth keeping — a long-overdue catch-up with
friends, a work meeting, any setting — by recording audio **on demand**, then:

- transcribing it and figuring out **who said what**,
- extracting **structured insights** (what was discussed, decided, promised), and
- **ingesting it into a knowledge graph** that links people, topics, and commitments
  **across many conversations**, so the value **compounds over time**
  (e.g. "show me everything tied to Alice across every talk we've had").

A mobile capture app is the eventual front-end, but we are building the **backend
pipeline first** to prove the magic with uploaded audio.

> **Product note (don't forget):** recording real conversations has real
> consent/legal constraints — many jurisdictions require all-party consent. This
> shapes the eventual capture UX. Out of scope for the backend MVP, but real.

---

## 2. Decisions already made (please don't relitigate)

| Decision | Choice | Notes |
|---|---|---|
| Relationship to this repo | **Separate project** | Lives in its own `talkgraph/` folder, isolated from the unrelated "Society Maintenance WhatsApp Bot" that already exists in this repo. Same git repo only because the session was scoped to it; easy to extract later. |
| First milestone | **Backend pipeline first** | Upload audio → transcript → diarization → insights → graph. No mobile app yet. |
| Knowledge graph | **Cross-conversation graph now (Neo4j)** | Entity resolution from the start, so people/topics merge across conversations. |
| Speech-to-text | **OpenAI APIs** (user has the key) | Whisper for transcription. |
| Diarization | **LLM-based attribution (MVP), swappable** | OpenAI has **no native diarization**, so an LLM labels speakers from transcript text — *approximate* (separates by what's said, not by voice). A `Diarizer` interface lets pyannote/AssemblyAI drop in later. |
| Insight extraction | **OpenAI GPT-4o structured outputs** | One provider for the MVP; pluggable to Claude. |

---

## 3. What's been built (`talkgraph/`)

Pipeline: `ingest → transcribe → diarize → extract → graph-merge → query`. Each stage
sits behind a swappable interface (a `Protocol`), wired together by an `Orchestrator`.

```
talkgraph/
  pyproject.toml          # Python 3.10+, hatchling; deps: fastapi, uvicorn, openai, neo4j, pydantic(-settings)
  docker-compose.yml      # Neo4j 5 (bolt :7687, browser :7474, auth neo4j/talkgraph-dev)
  .env.example            # OPENAI_API_KEY, model names, NEO4J_*, DATA_DIR
  src/talkgraph/
    settings.py           # pydantic-settings, env-driven config
    models.py             # Pydantic models incl. the OpenAI structured-output schemas
    storage.py            # local filesystem store for audio + transcript JSON
    main.py               # FastAPI app + lifespan (inits OpenAI client + Neo4j, ensures constraints)
    pipeline/
      transcribe.py       # STTProvider + OpenAISTTProvider (Whisper verbose_json → segments)
      diarize.py          # Diarizer + LLMDiarizer (speaker attribution) + _apply() labeling
      extract.py          # InsightExtractor + OpenAIInsightExtractor (GPT-4o structured output)
      orchestrator.py     # Orchestrator (runs the stages) + GraphStore protocol
    graph/
      store.py            # Neo4jGraphStore: ingest (entity-resolution MERGE) + queries; normalize_name()
    api/
      routes.py           # POST /conversations, GET /conversations/{id}, /people/{name}, /commitments
  scripts/
    run_sample.py         # run pipeline on --audio or --transcript fixture; --no-graph to skip Neo4j
  examples/
    conversation_a.json   # pre-labeled + pre-extracted fixture (Alice & Bob)
    conversation_b.json   # later talk (Alice & Carol) — shares "Alice" + "remote work"
  tests/                  # 7 hermetic tests (no network/DB): orchestrator, diarize, normalize, graph params
  HANDOFF.md              # teleport-based handoff
  CONTINUATION.md         # this doc
```

### Graph model (the heart of it)
- **Nodes:** `Person {key, name}`, `Conversation {id, title, summary, date, source,
  transcript, audio_path, duration, action_items, notable_quotes(JSON)}`,
  `Topic {key, name}`, `Commitment {text, owner, due, status, conversation_id}`,
  `Decision {text, conversation_id}`.
- **Relationships:** `(Person)-[:PARTICIPATED_IN]->(Conversation)`,
  `(Conversation)-[:ABOUT]->(Topic)`, `(Person)-[:MADE]->(Commitment)`,
  `(Commitment)-[:IN]->(Conversation)`, `(Conversation)-[:REACHED]->(Decision)`.
- **Entity resolution (the compounding mechanic):** people and topics are `MERGE`d by
  a normalized key (`normalize_name` = lowercase + trim + collapse whitespace), so a
  new conversation links into the existing graph instead of duplicating nodes.
  Uniqueness constraints exist on `Person.key`, `Conversation.id`, `Topic.key`.

---

## 4. Current state / what's verified

- ✅ **7 hermetic tests pass** (`pytest`): orchestrator wiring, diarization label
  assignment, name normalization, and graph **ingest param/keying logic** (via a fake
  Neo4j driver) + person-view post-processing.
- ✅ App imports; all routes register; OpenAI SDK structured-output API
  (`beta.chat.completions.parse`) present; **pipeline runs offline** on a fixture.
- ⚠️ **NOT verified: live Neo4j** — the cloud sandbox had no Docker daemon. Running
  the real graph demo on local Docker is the **immediate next step**.
- ⚠️ **NOT verified: real OpenAI calls** on actual audio (STT/diarization/extraction).

---

## 5. Get the code (no teleport)

Repo `harshit0605/Hbc_whatsapp_claw`, branch **`claude/inspiring-volta-ctl9O`**.

Fresh clone:
```bash
git clone https://github.com/harshit0605/Hbc_whatsapp_claw.git
cd Hbc_whatsapp_claw
git checkout claude/inspiring-volta-ctl9O
```
Already have a clone:
```bash
git fetch origin claude/inspiring-volta-ctl9O
git checkout claude/inspiring-volta-ctl9O
git pull origin claude/inspiring-volta-ctl9O
```
All project files live under the `talkgraph/` subdirectory.
**Keep working on this branch; commit and push here.**

---

## 6. Run + verify locally (Docker Neo4j + OpenAI key)

```bash
cd talkgraph
cp .env.example .env            # set OPENAI_API_KEY (only needed for real audio/LLM runs)
docker compose up -d            # local Neo4j: bolt :7687, browser http://localhost:7474 (neo4j / talkgraph-dev)
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                # expect: 7 passed
```

**Cross-conversation graph demo** (no OpenAI key needed — fixtures are pre-labeled &
pre-extracted, so this exercises diarization-skip + the real graph):
```bash
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_a.json
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_b.json
```
Expected: after the 2nd run, the printed **GRAPH VIEW: Alice** shows she participated
in **both** conversations, with topics, commitments, and co-participants (Bob *and*
Carol) merged across them. Explore visually at http://localhost:7474.

**Real pipeline on your own audio** (needs `OPENAI_API_KEY` in `.env`):
```bash
.venv/bin/python scripts/run_sample.py --audio /path/to/recording.m4a
```
**Or run the API:**
```bash
.venv/bin/uvicorn talkgraph.main:app --reload
# POST a file to /conversations (multipart field 'file'); then GET /people/{name}, /commitments
```

---

## 7. Remaining tasks / next directions

1. **Verify the live graph** (the §6 demo) against real Neo4j — confirm entity
   resolution links Alice across both talks. (Only thing still unverified.)
2. Then pick a direction:
   - **(a) Sharper diarization** — implement a real acoustic `Diarizer` (pyannote
     locally, or AssemblyAI) and swap it into `pipeline/diarize.py`.
   - **(b) Capture surface** — a mobile recorder app, or a quick WhatsApp voice-note
     bootstrap to feel the magic without building an app yet.
   - **(c) Richer graph queries** — topic timelines, per-person open commitments,
     "what did X and Y discuss," clustering.
3. **Hardening later:** durable storage for transcripts/insights if Neo4j props
   aren't enough; auth; multi-user; LLM cost controls; the consent/legal capture UX.

---

## 8. Known seams & gotchas
- **Diarization is approximate** (LLM, not acoustic) — by design for the MVP.
- **STT model:** `whisper-1` is the default because it returns segment timestamps;
  `gpt-4o-transcribe` is higher quality but returns no segments.
- **Structured-output models** in `models.py` deliberately avoid default values
  (strict schemas require all fields present; optionality = nullable types).
- Audio + transcript JSON live on local disk (`DATA_DIR`); the full transcript text is
  also stored as a `Conversation.transcript` property in Neo4j.

---

## 9. Kickoff prompt for the new thread

> Read `talkgraph/CONTINUATION.md` — we're continuing this project. First, bring up
> local Neo4j (`docker compose up -d` in `talkgraph/`), install deps, run `pytest`,
> then run the cross-conversation demo with both example fixtures and confirm the
> graph links "Alice" across both conversations. Report what you see, then propose
> the next step.
