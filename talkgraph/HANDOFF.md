# Handoff: continue the `talkgraph` build on your local Mac

This brief explains how to (1) pull this Claude Code **cloud session** down to your
**local Mac** with full context, and (2) run the `talkgraph` pipeline against a
**local Neo4j (Docker)** — the one step that could not run in the cloud sandbox.

It is self-contained: you can paste it into a new thread to bootstrap context, or
just follow Steps 1–3 yourself.

---

## Context — what this project is

`talkgraph/` is a fresh, standalone backend that turns conversation audio into a
compounding knowledge graph:

```
ingest → transcribe → diarize → extract → graph-merge → query
```

- **transcribe** — OpenAI Whisper (`src/talkgraph/pipeline/transcribe.py`)
- **diarize** — LLM-based speaker attribution behind a swappable `Diarizer`. OpenAI
  has no native diarization, so labels are *approximate* for now; the seam lets us
  drop in pyannote/AssemblyAI later (`pipeline/diarize.py`)
- **extract** — GPT-4o structured outputs → title, summary, participants, topics,
  decisions, commitments, action items, quotes (`pipeline/extract.py`, `models.py`)
- **graph** — Neo4j with **entity resolution on ingest**: people/topics MERGE by
  normalized key, so each new conversation links into existing nodes instead of
  duplicating them (`graph/store.py`)
- **API** — `POST /conversations`, `GET /conversations/{id}`, `GET /people/{name}`,
  `GET /commitments` (`api/routes.py`)

### Status
- ✅ 7 hermetic tests pass; app imports; pipeline runs offline on fixtures.
- ⚠️ **Live Neo4j not yet verified** — the cloud sandbox had no Docker daemon.
  Running the real graph demo on local Docker is the immediate next step.
- ⚠️ Real OpenAI calls (STT/extraction on actual audio) not yet exercised end-to-end.

### Coordinates
- Repo: `harshit0605/Hbc_whatsapp_claw`
- Branch: `claude/inspiring-volta-ctl9O`
- Cloud session: https://claude.ai/code/session_012mrssLpeAoJ67Px6DN3L8n

---

## Step 1 — Teleport this session to your Mac

`--teleport` pulls the cloud session's **branch *and* full conversation history**
into your local terminal. (This is different from `--resume`, which only reopens
conversations already in your machine's local history.)

**Prerequisites (one-time):**
- Install Claude Code and sign in to the **same claude.ai account** as this session
  — https://code.claude.com/docs/en/quickstart (run `/login` if you are authed via
  API key / Bedrock / Vertex; teleport requires claude.ai subscription auth).
- Have a local clone of `harshit0605/Hbc_whatsapp_claw` with a **clean working tree**
  (commit or stash local changes first).

**Do it (pick one):**
- **From the web UI:** in this session at claude.ai/code, click **"Open in CLI"** —
  it copies a `claude --teleport <session-id>` command. Paste it into your Mac
  terminal from inside the repo clone.
- **From the CLI:** `claude --teleport` for an interactive picker, then choose this
  session (or `claude --teleport <session-id>` to go straight to it).
- **Inside an existing CLI session:** `/teleport` (alias `/tp`).
- **From `/tasks`:** press `t` on the session.

On teleport, Claude verifies you are in the correct repo, fetches and checks out
`claude/inspiring-volta-ctl9O`, and loads the conversation history.

**Caveat:** cloud sessions expire after inactivity. If you see
*"environment has expired,"* the code is still safe on the branch — just:
```bash
git fetch origin claude/inspiring-volta-ctl9O
git checkout claude/inspiring-volta-ctl9O
```
You would lose only the live chat context, not the work.

---

## Step 2 — Run the pipeline against local Neo4j (Docker)

From the repo root on your Mac:

```bash
cd talkgraph
cp .env.example .env            # set OPENAI_API_KEY (only needed for real audio/LLM runs)
docker compose up -d            # local Neo4j: bolt :7687, browser http://localhost:7474
                                # (login neo4j / talkgraph-dev)
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                # expect: 7 passed
```

**Cross-conversation graph demo** (no OpenAI key needed — the fixtures are already
speaker-labeled and pre-extracted, so this exercises only diarization-skip + graph):
```bash
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_a.json
.venv/bin/python scripts/run_sample.py --transcript examples/conversation_b.json
```
After the second run, the printed **GRAPH VIEW: Alice** should show she participated
in **both** conversations, with topics, commitments, and co-participants (Bob *and*
Carol) merged across them. That is the core thesis: the graph compounds. You can also
explore it visually in the Neo4j browser at http://localhost:7474.

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

## Step 3 — Next tasks (pick a direction)

1. **Verify the live graph** (the Step 2 demo) — confirm entity resolution links
   Alice across both talks. This is the one thing still unverified.
2. Then choose a direction:
   - **(a) Sharper diarization** — drop pyannote (local) or AssemblyAI into the
     `Diarizer` seam in `pipeline/diarize.py`.
   - **(b) Capture surface** — a mobile recorder, or a WhatsApp voice-note bootstrap.
   - **(c) Richer graph queries** — topic timelines, clusters, per-person open
     commitments, "what did X and Y discuss."
