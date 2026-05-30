# Phase D — WhatsApp voice-note capture via society-bot (plan, not yet built)

> **State:** designed, not implemented. The cheap file-forwarding bootstrap
> shipped in Phase C (`scripts/ingest_voice_note.py`); this doc is the plan
> for the live-WhatsApp wire that follows.
>
> **How to use this doc:** a fresh agent with no context should be able to
> execute the implementation order in §8 by reading this file plus
> `CONTINUATION.md`. Citations point to real files in this repo.

---

## 1. Goal

When you send a voice note in WhatsApp with the marker word `#capture`
(anywhere in the voice-note's caption or in the text message immediately
before/after), the audio is forwarded to talkgraph's `/conversations`
endpoint, extracted into the knowledge graph, and the bot replies with a
short summary including any commitments captured.

Everything else the society-bot does continues to work unchanged — talkgraph
capture is purely additive.

## 2. Architecture (one diagram)

```
   WhatsApp (Baileys/Web)                          talkgraph
        │                                              ▲
        ▼                                              │  POST /conversations
   ┌───────────────────────────┐                      │  (multipart audio +
   │   OpenCLAW gateway        │                      │   participant_hint)
   │   infra/openclaw/         │                      │
   │                           │                      │
   │   plugins/                │                      │
   │     audit_logger.py       │                      │
   │     language_detect.py    │                      │
   │     media_handler.py  ────┼── stores raw audio ──┘  ┌──────────────────┐
   │     talkgraph_capture.py ◄┼── reads marker word + ──┤ Neo4j (talkgraph │
   │       (NEW — Phase D)     │   storage_key,           │  Docker         │
   │     ...                   │   posts to talkgraph     │  container)     │
   └───────────────────────────┘                          └──────────────────┘
        │                                              │  short reply ◄────┘
        ▼   ◄─────── dispatch.send_text() ────────────  │
   WhatsApp reply ("captured: <title>; <commitment> ; ...")
```

talkgraph stays on its own Neo4j and pyproject. The plugin is the only new
file in `infra/openclaw/`. Cross-service communication is plain HTTP, so the
§2 "isolated" decision still mostly holds — the coupling is at deploy time
(network reachability), not at code time.

## 3. The two services that have to talk

| Caller | Callee | Method | Path | Auth |
|---|---|---|---|---|
| `talkgraph_capture` plugin | skills service | `GET` | `/media/{key}` (need to verify exists) | `Authorization: Bearer $SKILLS_API_TOKEN` |
| `talkgraph_capture` plugin | talkgraph API | `POST` | `/conversations` (multipart `file` + `participant_hint`) | `Authorization: Bearer $TALKGRAPH_API_TOKEN` |
| `talkgraph_capture` plugin | OpenCLAW outbound gateway | `POST` (via `dispatch.send_text` adapter — or its own httpx call) | (uses society-bot's existing send-reply path) | as `dispatch.send_text` already does |

**Open question for D-day:** does the skills service expose a `GET /media/{key}`
fetch endpoint? `media_handler.py:83-92` only shows `POST /media` (upload).
The plugin will need either (a) a new fetch endpoint on skills, or (b) to
fetch directly from S3 using credentials shared with the skills service, or
(c) to download the media itself via `ctx.media.download()` and bypass
society-bot's storage entirely (cleanest — see §5 option-A below).

## 4. What changes in talkgraph

1. **Bearer auth on `POST /conversations`.** Currently un-authed
   ([routes.py:11](src/talkgraph/api/routes.py:11)). Add a dependency:

   ```python
   # src/talkgraph/api/auth.py (new)
   from fastapi import Depends, Header, HTTPException
   from ..settings import get_settings

   def require_api_token(authorization: str = Header(default="")) -> None:
       token = get_settings().api_token
       if not token:
           return  # auth disabled (dev mode)
       expected = f"Bearer {token}"
       if authorization != expected:
           raise HTTPException(status_code=401, detail="invalid api token")
   ```

   Apply to `POST /conversations` only (read endpoints stay open for now;
   tighten later if you ever expose talkgraph publicly).

2. **`TALKGRAPH_API_TOKEN` setting** in `settings.py` + `.env.example`.
   If unset, the dependency above is a no-op (dev-mode default).

3. **Optional `participant_hint`** form field on `POST /conversations`. Wire
   it through `Orchestrator.process_audio` → `LLMDiarizer.diarize` as a
   prompt hint so GPT-4o's speaker labelling can prefer the known sender's
   name when guessing. Backward-compatible: callers without the hint behave
   exactly as today.

4. **Health endpoint** — `GET /healthz` returning 200 + neo4j ping. The
   plugin uses this to fail fast if talkgraph is down.

5. **No changes to the graph schema**; existing `source` field already
   distinguishes `whatsapp-bootstrap` (Phase C) from `whatsapp-live`
   (Phase D, new value).

Tests: extend `test_ingest_voice_note.py`-style hermetic coverage for the
auth dependency; the participant-hint plumbing tests should mock the
diarizer.

## 5. The plugin (`infra/openclaw/plugins/talkgraph_capture.py`)

Follows the same shape as the existing plugins
([media_handler.py:1-66](../infra/openclaw/plugins/media_handler.py:1) is the
closest analogue: it's the other plugin that consumes inbound audio).

### Trigger

```
marker = os.environ.get("TALKGRAPH_CAPTURE_MARKER", "#capture")
```

A voice note is captured iff EITHER:
- the voice-note message body contains `marker` (caption case), OR
- a text message containing `marker` arrived from the same JID within the
  last `TALKGRAPH_CAPTURE_WINDOW_SEC` seconds (default 60).

Trailing-text and leading-text are both supported. The plugin keeps a tiny
per-JID LRU dict of `(timestamp, marker_seen)` — no persistence, in-memory
only. State that doesn't survive a restart is fine; capture is opt-in per
voice note anyway.

### Lifecycle

```python
# infra/openclaw/plugins/talkgraph_capture.py (sketch)
async def on_message_received(ctx, message):
    if not _is_voice_note(message):
        _maybe_remember_marker(message)
        return message  # not for us
    if not _marker_active_for(message):
        return message

    # Option A (recommended): pull audio bytes directly from OpenCLAW.
    audio = await _download_audio_via_ctx(ctx, message)  # mirrors media_handler._fetch_media

    # Spawn the capture as a background task — extraction takes 10-30s for
    # a long voice note; we don't want to block the message turn.
    asyncio.create_task(_capture_and_reply(ctx, message, audio))
    return message
```

### `_capture_and_reply`

1. Send an immediate "🔖 captured, working on it…" reaction or short text
   so the user sees acknowledgement.
2. `POST $TALKGRAPH_API_URL/conversations` with multipart `file=<audio>` and
   `participant_hint=<sender display name>`. `Authorization: Bearer
   $TALKGRAPH_API_TOKEN`.
3. On 200: format `insights.title`, `summary`, the first 2 commitments, and
   send via `dispatch.send_text(message["from"], body=...)` (the existing
   helper at `services/skills/src/society_skills/dispatch.py:29-69`).
4. On failure (network, 4xx, 5xx, timeout): friendly error message; details
   to `audit_logger` (already running).

### Why option A (download via ctx) over option B (refetch from S3)

- **Avoids the unknown `GET /media/{key}` question** entirely. No new skills
  endpoint required.
- **Decouples plugin order** — `talkgraph_capture` doesn't have to run
  after `media_handler`, so the existing plugin pipeline is unchanged.
- **The blob is in memory once** — both `media_handler` (society-bot's
  pipeline) and `talkgraph_capture` (talkgraph's pipeline) do their own
  thing with it. Yes the audio is fetched twice, but voice notes are small
  (<5 MB typical) so the cost is negligible.

If duplicate downloads become a concern later, switch to option B: share
the storage key from `media_handler` via `message.setdefault("storage_keys",
[])` (which media_handler already populates on
[line 61](../infra/openclaw/plugins/media_handler.py:61)).

## 6. The plugin's config entry

Append to [infra/openclaw/config.yaml:42](../infra/openclaw/config.yaml:42):

```yaml
- name: talkgraph_capture
  path: ./plugins/talkgraph_capture.py
  env:
    TALKGRAPH_API_URL: ${TALKGRAPH_API_URL}        # e.g. http://host.docker.internal:8000
    TALKGRAPH_API_TOKEN: ${TALKGRAPH_API_TOKEN}
    TALKGRAPH_CAPTURE_MARKER: ${TALKGRAPH_CAPTURE_MARKER:-#capture}
    TALKGRAPH_CAPTURE_WINDOW_SEC: ${TALKGRAPH_CAPTURE_WINDOW_SEC:-60}
    OPENCLAW_OUTBOUND_URL: ${OPENCLAW_OUTBOUND_URL}
    OPENCLAW_OUTBOUND_TOKEN: ${OPENCLAW_OUTBOUND_TOKEN}
```

## 7. Docker networking

Two options; pick at implementation time based on whether talkgraph and
society-bot run on the same machine.

| Option | OpenCLAW reaches talkgraph at | When to use |
|---|---|---|
| **(a) host.docker.internal (Recommended)** | `http://host.docker.internal:8000` | Mac dev, same-host prod. Talkgraph stays in its own `docker-compose.yml`; OpenCLAW just makes outbound HTTP. Cleanest isolation. |
| **(b) shared compose network** | `http://talkgraph-api:8000` (service name) | If you'd rather run both stacks from one compose file. Tighter, but couples deploy. |
| **(c) talkgraph as sub-service of society-bot** | (inline) | Avoid — violates §2's "separate project" decision. |

Default to (a). Document the env value in `.env.example` for both projects.

## 8. Implementation order

| Step | What | Files |
|---|---|---|
| D1 | Add `api_token` setting + Bearer dependency; gate POST /conversations | `src/talkgraph/settings.py`, `src/talkgraph/api/auth.py` (new), `src/talkgraph/api/routes.py`, `.env.example`, `tests/test_auth.py` (new) |
| D2 | `participant_hint` param plumbed through orchestrator → diarizer | `src/talkgraph/api/routes.py`, `src/talkgraph/pipeline/orchestrator.py`, `src/talkgraph/pipeline/diarize.py`, hermetic tests |
| D3 | `GET /healthz` (200 + neo4j verify) | `src/talkgraph/api/routes.py` |
| D4 | Write the plugin (option A: download via ctx) with the marker-window state machine | `infra/openclaw/plugins/talkgraph_capture.py` |
| D5 | Plugin config + env in compose | `infra/openclaw/config.yaml`, root `docker-compose.yml`, both `.env.example`s |
| D6 | Test via `scripts/simulate_inbound.py` (Explore agent surfaced this — it drives MCP tools directly, bypassing real WhatsApp) | local |
| D7 | End-to-end test with a real voice note from a paired phone | local |

D1, D2, D3 are pure talkgraph changes — can ship in their own commits.
D4–D7 are the actual coupling step; merge once D1-D3 are green.

## 9. Failure modes the plugin must handle

| Failure | Behaviour |
|---|---|
| `TALKGRAPH_API_URL` unset | Plugin skips silently with a one-line audit log; no user reply |
| Talkgraph returns 401 | Reply "capture not authorised — check TALKGRAPH_API_TOKEN" |
| Talkgraph times out (>60s for long audio?) | Reply "capture is slow, will retry when audio finishes processing" — *don't* retry server-side, surface to user |
| Whisper rejects audio (>25 MB) | Talkgraph returns a structured error; plugin relays "voice note too long (>25 MB)" |
| Marker timed out before voice note | Plugin treats voice note as not-for-it; original message flow is unchanged |

## 10. Privacy / consent (don't skip this section)

The CONTINUATION.md §1 product note: "recording real conversations has real
consent/legal constraints — many jurisdictions require all-party consent."
The marker-word trigger is the policy: capture is opt-in per voice note,
the user has to explicitly type `#capture` for it to happen. Document this
in the bot's `/help` command output and in the README.

For Phase D2 (out of scope here): an audit endpoint that lists all
conversations a given JID has captured, with a delete button.

## 11. What this plan deliberately does *not* cover

- Multi-tenant talkgraph (separate graphs per user / group)
- Sharing graph views back over WhatsApp ("show me what Alice and I have
  talked about") — feasible but a separate phase
- Re-running extraction with a corrected transcript / participant hint
- WhatsApp group support (today only direct messages are captured)
- Cloud-API path (Meta business account) as an alternative to Baileys

## 12. Kickoff prompt for the next thread

> Read `talkgraph/PHASE_D_PLAN.md`. Execute steps D1-D3 in order, one
> commit per step, and stop. Run pytest after each. Do not start D4 until
> the user confirms — D4 is where the coupling to society-bot begins.
