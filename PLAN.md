# Society Maintenance WhatsApp Bot — Implementation Plan

> A WhatsApp-first maintenance assistant for a multi-tower residential society,
> built on the **OpenCLAW** agent platform. Residents report issues in plain
> language (text / voice / photo) in English, Hindi, or regional languages.
> Admins triage from a web portal and dispatch tasks to workers via WhatsApp
> after explicit approval.

---

## 1. Problem & goals

A newly-built society with ~8–9 towers, 20 floors each, has frequent
maintenance issues (plumbing, electrical, lift, cleanliness, garbage). Today
those reports are lost in informal WhatsApp groups. We want:

1. A single WhatsApp number every resident can message.
2. Free-form input (text, voice notes, photos) in their preferred language.
3. Automatic classification + ticketing + status tracking.
4. Critical issues (gas leak, lift trapped, fire, water flooding) escalated to
   admins on WhatsApp in real time.
5. An admin web portal to triage, assign, and approve dispatches.
6. Worker dispatch over WhatsApp — only after an admin presses "Approve".
7. A long-lived resident + worker directory that grows with use.

---

## 2. Why OpenCLAW

OpenCLAW gives us, out of the box:

- A WhatsApp gateway via **Baileys (WhatsApp Web protocol)** — no Meta
  Business API approval needed for the pilot.
- Native handling of inbound **text, voice (auto-transcribed), images,
  documents, location, vCards**.
- Per-DM and per-group session isolation, so resident chats stay separate
  from the worker group and admin alert channel.
- An **MCP skills** mechanism — our business logic (DB writes, dispatch,
  approvals) becomes a small set of agent-callable tools.
- **Plugin hooks** for cross-cutting concerns (language detection, audit
  logging, critical-alert routing) without changing the agent prompt.

### Constraints we have to design around

| Constraint | Impact | Mitigation |
|---|---|---|
| Baileys outbound is allowlist-gated (`allowFrom` / `dmPolicy`) | Bot can't message a number it has never seen | Residents DM first → JID learned; workers + admins are onboarded by the admin portal which pre-registers their numbers into the allowlist. |
| One WhatsApp Web session = one phone number | Doesn't scale beyond pilot society | Architect the skills layer to be channel-agnostic; later we can swap the channel to WhatsApp Business API without touching the database or admin portal. |
| No native interactive buttons / list messages on Baileys | UX has to be text-driven | Use numbered quick-reply menus ("Reply 1 for plumbing, 2 for electrical…") plus free text. |
| Voice notes transcribed inside OpenCLAW | Transcript quality varies by language | Have the agent confirm the parsed intent back to the user before creating a complaint. |
| Media size cap 50 MB | Fine for photos, may bite long videos | Reject videos >50 MB with a friendly message. |

---

## 3. High-level architecture

```
                    ┌──────────────────────────────────────────────┐
                    │              Residents (WhatsApp)            │
                    │   text / voice / photo / Hindi / English…    │
                    └──────────────────────────┬───────────────────┘
                                               │
                                               ▼
                  ┌────────────────────────────────────────────────┐
                  │  OpenCLAW Agent  (Baileys gateway + LLM brain) │
                  │  • per-DM session per resident                 │
                  │  • plugin: language_detect                     │
                  │  • plugin: audit_logger                        │
                  │  • plugin: critical_alert_router               │
                  └────┬──────────────────────┬────────────────────┘
                       │ MCP skills (stdio)   │ outbound msgs
                       ▼                      │
        ┌──────────────────────────────┐      │
        │  society-skills MCP server   │      │
        │  (Python, FastMCP)           │      │
        │  • register_or_get_resident  │      │
        │  • create_complaint          │      │
        │  • attach_media              │      │
        │  • classify_severity         │      │
        │  • list_workers_by_category  │      │
        │  • propose_dispatch          │      │
        │  • send_dispatch_to_worker   │      │
        │  • update_complaint_status   │      │
        │  • escalate_to_admin         │      │
        └─────┬──────────────────┬─────┘      │
              │                  │            │
              ▼                  ▼            │
       ┌─────────────┐    ┌─────────────┐     │
       │  Postgres   │    │  S3 / R2    │     │
       │  (data)     │    │  (photos)   │     │
       └─────▲───────┘    └─────────────┘     │
             │                                │
             │ same DB / API                  │
             │                                │
    ┌────────┴─────────────┐                  │
    │   Admin Web Portal   │                  │
    │   (Next.js + tRPC)   │                  │
    │   • triage queue     │                  │
    │   • assign + APPROVE │──── approval ────┘
    │   • directories      │      triggers
    │   • analytics        │      outbound WA
    └──────────────────────┘      to worker
```

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Agent runtime | **OpenCLAW** (self-hosted) | Native WhatsApp channel + MCP skills + plugin hooks. |
| LLM | **Claude Sonnet 4.6** for conversation, **Claude Haiku 4.5** for classification/severity | Sonnet handles multilingual ambiguity well; Haiku is cheap enough to run on every inbound for cls/severity. Both via the Claude API. |
| Skills server | **Python 3.12 + FastMCP** | MCP server pattern matches OpenCLAW's skills model; Python ecosystem is best for ad-hoc LLM/image work. |
| API & worker dispatch | **FastAPI** (shares process with FastMCP) | One Python service exposes both MCP (stdio) and an HTTP API consumed by the admin portal. |
| Database | **PostgreSQL 16** | Relational core (residents, towers, flats, complaints, workers, assignments) + JSONB for raw LLM payloads and conversation transcripts. |
| File store | **Cloudflare R2** (or MinIO for local dev) | S3-compatible; pre-signed URLs for the admin portal photo viewer. |
| Admin portal | **Next.js 15 (App Router) + Tailwind + shadcn/ui + tRPC** | Type-safe end-to-end, fast to build, easy auth with NextAuth or Clerk. |
| Auth (portal) | **Clerk** or NextAuth credentials | Few admins, simple needs. |
| Background jobs | **Postgres + `pg-boss`** (or `arq` on Python side) | Reminders to residents, SLA escalations, retry of WhatsApp sends. |
| Hosting (pilot) | A single 4 GB VPS (Hetzner / DigitalOcean) running Docker Compose | Cheap, repeatable; later move to managed Postgres + container hosting. |
| Observability | **Loki + Grafana** or hosted (Axiom / Logtail) | Visibility into agent turns, classifier outputs, and dispatch flows. |

---

## 5. Data model (PostgreSQL)

Simplified — full DDL lives under `db/migrations/`.

```sql
-- buildings
create table tower (
  id              serial primary key,
  name            text not null unique,     -- "Tower A", "Tower B" …
  floors          int  not null
);

-- residents (one row per WhatsApp number; one resident may own multiple flats)
create table resident (
  id              uuid primary key default gen_random_uuid(),
  wa_jid          text unique not null,     -- "9198xxxxxxxx@s.whatsapp.net"
  phone           text unique not null,
  display_name    text,
  language        text default 'en',        -- 'en' | 'hi' | 'mr' | …
  status          text default 'pending',   -- 'pending' | 'verified' | 'blocked'
  created_at      timestamptz default now()
);

create table flat (
  id              serial primary key,
  tower_id        int references tower(id),
  flat_number     text not null,            -- "1804"
  unique (tower_id, flat_number)
);

create table resident_flat (
  resident_id     uuid references resident(id) on delete cascade,
  flat_id         int  references flat(id),
  role            text default 'tenant',    -- 'owner' | 'tenant' | 'family'
  primary key (resident_id, flat_id)
);

-- workers
create table worker (
  id              uuid primary key default gen_random_uuid(),
  wa_jid          text unique,
  phone           text unique not null,
  name            text not null,
  categories      text[] not null,          -- {'plumbing','electrical'}
  is_active       bool default true,
  notes           text
);

-- complaints
create type complaint_status as enum (
  'open','triaging','assigned','in_progress','resolved','closed','rejected'
);
create type complaint_severity as enum ('low','medium','high','critical');

create table complaint (
  id              uuid primary key default gen_random_uuid(),
  ticket_no       serial unique,            -- human-friendly "#1042"
  resident_id     uuid references resident(id),
  flat_id         int  references flat(id),
  tower_id        int  references tower(id),
  category        text not null,            -- plumbing | electrical | lift | cleanliness | garbage | security | other
  severity        complaint_severity not null default 'low',
  status          complaint_status   not null default 'open',
  title           text not null,            -- LLM-generated short title
  description     text not null,            -- normalized text (original or transcribed)
  raw_input       jsonb,                    -- {language, transcript, original_text, …}
  created_at      timestamptz default now(),
  updated_at      timestamptz default now(),
  resolved_at     timestamptz
);

create table complaint_media (
  id              uuid primary key default gen_random_uuid(),
  complaint_id    uuid references complaint(id) on delete cascade,
  kind            text not null,            -- 'image' | 'audio' | 'video' | 'document'
  storage_key     text not null,            -- R2 object key
  mime            text,
  bytes           int
);

-- worker assignments (only created after admin approval)
create table assignment (
  id              uuid primary key default gen_random_uuid(),
  complaint_id    uuid references complaint(id),
  worker_id       uuid references worker(id),
  approved_by     uuid references admin_user(id),
  status          text default 'pending',   -- pending | accepted | done | cancelled
  dispatched_at   timestamptz default now(),
  closed_at       timestamptz,
  notes           text
);

create table admin_user (
  id              uuid primary key default gen_random_uuid(),
  email           text unique not null,
  wa_phone        text,                     -- for critical alerts
  role            text default 'admin',     -- 'admin' | 'super_admin'
  created_at      timestamptz default now()
);

-- full audit trail of WhatsApp messages
create table message_log (
  id              bigserial primary key,
  direction       text not null,            -- 'in' | 'out'
  wa_jid          text not null,
  resident_id     uuid references resident(id),
  worker_id       uuid references worker(id),
  body            text,
  media_keys      text[],
  meta            jsonb,
  created_at      timestamptz default now()
);
```

---

## 6. Conversation flows

### 6.1 First-time resident onboarding

```
Resident → bot:    "kitchen sink leak ho raha hai"  (Hindi text)
bot:              "Namaste! Naye user hain aap. Pehle thoda details chahiye:
                   Aap kaunse tower mein rehte hain?  (e.g. Tower A)"
Resident:         "tower B"
bot:              "Tower B. Flat number?"
Resident:         "1804"
bot:              "Aapka naam?"
Resident:         "Rohit Sharma"
bot:              "Confirm: Rohit Sharma, Tower B – 1804. Sahi hai?  (Reply YES/NO)"
Resident:         "yes"
bot:              "Done! Aapki complaint bhi note kar li hai —
                   Ticket #1042, plumbing. Aapko status update milega yahin."
                  (also routes the complaint into the triage queue)
```

Implementation note: the agent's system prompt instructs it to call
`register_or_get_resident` on every turn (it's idempotent and returns the
existing record if the resident is already known), then branch on
`status == 'pending'` to collect missing fields.

### 6.2 Returning resident reports an issue (voice + photo)

```
Resident → bot:   [voice note in Hindi]  +  [photo of overflowing dustbin]
                  OpenCLAW transcribes:
                  "humare floor ke corridor mein kachra do din se pada hai"
bot:              calls classify_severity(text, photo_caption)
                       → category=garbage, severity=medium
                  calls create_complaint(...)  → ticket #1043
bot:              "Mil gaya. Ticket #1043 (Garbage) raise kar di hai —
                   Tower B, floor 18. Admin ko bhej diya, jaldi resolve hoga."
```

### 6.3 Critical issue → admin alert

```
Resident:         "lift mein phas gaya hu, Tower A!"
bot:              classify_severity → critical
bot:              create_complaint(severity=critical)
                  escalate_to_admin(complaint_id, channel='whatsapp')
bot → resident:   "Help is on the way. Admin ko abhi alert kar diya hai.
                   Aap calm rahein, koi bhi switch press na karein."
bot → admin WA:   "🚨 CRITICAL: Lift trapped — Tower A, resident Rohit Sharma
                   (Tower B – 1804, +91-98xxx). Ticket #1044.  Take action."
```

### 6.4 Admin triage + worker dispatch

1. Admin opens the portal → sees Ticket #1043 in **Open** queue.
2. Portal suggests workers based on `category=garbage` and current load.
3. Admin clicks **Assign → Ramesh (Housekeeping)**.
4. Admin clicks **Approve & Dispatch** (this is the human-in-the-loop gate).
5. Portal calls API `POST /assignments/{id}/dispatch`.
6. API calls the `send_dispatch_to_worker` skill via the OpenCLAW agent's
   outbound channel (or directly via the gateway).
7. Worker Ramesh receives on WhatsApp:

   > Hi Ramesh, new task #1043 — Garbage overflow, Tower B, Floor 18, Flat
   > 1804. Reported by Rohit Sharma (+91-98xxx).
   > Reply **ACCEPT**, **DONE**, or **HELP**.
   > [photo attached]

### 6.5 Worker status update

```
Worker → bot:     "accept"
bot:              update_complaint_status(id, 'in_progress')
                  → notifies resident
bot → resident:   "Update on Ticket #1043: assigned worker has accepted —
                   should be resolved within ~2 hours."

Worker → bot:     "done" + [photo of cleaned corridor]
bot:              update_complaint_status(id, 'resolved')
bot → resident:   "Ticket #1043 closed by housekeeping. Rate the service
                   1–5 ⭐ (reply with a number) or send 'reopen' if not fixed."
```

---

## 7. Skills (MCP tools the agent will call)

All live in `services/skills/` and are exposed to OpenCLAW as a single
MCP server.

| Skill | Purpose | Key params |
|---|---|---|
| `register_or_get_resident` | Idempotent. Returns resident row by `wa_jid`; if missing, creates a `pending` stub. | `wa_jid`, `display_name?`, `tower?`, `flat?` |
| `update_resident_profile` | Fill in tower/flat/name/language during onboarding. | `resident_id`, `fields` |
| `create_complaint` | New ticket from current message + any attached media keys. | `resident_id`, `category`, `description`, `media_keys`, `raw_input` |
| `attach_media` | Upload media bytes to R2, return `storage_key`. (Called by a plugin so the agent doesn't see binary.) | `bytes`, `mime` |
| `classify_severity` | Wraps a Claude Haiku call. Returns `category`, `severity`, `confidence`. Deterministic JSON output. | `text`, `media_descriptions?` |
| `escalate_to_admin` | Sends formatted critical alert to the admin WhatsApp group/DM. | `complaint_id`, `reason` |
| `list_workers_by_category` | Read-only helper for the agent / portal. | `category`, `limit?` |
| `propose_dispatch` | Returns suggested worker ids for a complaint (load + category aware). | `complaint_id` |
| `send_dispatch_to_worker` | **Gated** — only callable from the portal's approve endpoint, never directly by the agent. Sends the WhatsApp message to the worker and writes an `assignment` row. | `complaint_id`, `worker_id`, `approved_by` |
| `update_complaint_status` | Status transitions w/ side effects (notify resident, close ticket). | `complaint_id`, `new_status`, `actor` |
| `search_complaints` | For admins and for the agent's "what's the status of my ticket" queries. | `resident_id?`, `status?`, `since?` |
| `record_resident_rating` | Stores 1–5 rating; reopens ticket if rating ≤ 2 with comment "not fixed". | `complaint_id`, `rating`, `comment?` |

The `send_dispatch_to_worker` skill is intentionally **not** exposed to the
agent's tool list — it lives in the MCP server but is reachable only via
authenticated HTTP from the admin portal. That enforces the
human-approval rule structurally, not just by prompt.

---

## 8. Plugins (OpenCLAW lifecycle hooks)

| Plugin | Hook | What it does |
|---|---|---|
| `language_detect` | `messageReceived` | Quick langdetect on inbound text; sets `session.locale`. The agent's system prompt reads this and responds in the same language. |
| `media_handler` | `messageReceived` | When `<media:image>` arrives, downloads bytes, uploads to R2, replaces the placeholder with `storage_key` so the agent only sees an opaque reference. |
| `audit_logger` | `messageReceived`, `messageSent` | Writes every turn to `message_log` for traceability. |
| `critical_alert_router` | `messageSent` | If the agent's outbound contains the structured marker `[CRITICAL_TICKET:<id>]`, also fan-out to the admin alert channel. (Belt-and-suspenders alongside `escalate_to_admin`.) |
| `worker_status_router` | `messageReceived` | If `wa_jid` matches a `worker.wa_jid` row, route the message into a worker-specific session/persona instead of the resident flow. |

---

## 9. Admin web portal (Next.js)

Routes:

- `/login` — Clerk / NextAuth
- `/queue` — open + triaging tickets (with filters: tower, category, severity)
- `/tickets/[id]` — full thread (resident conversation), media gallery,
  status timeline, **Assign worker** + **Approve & Dispatch** controls
- `/residents` — directory with search, language, flat history
- `/workers` — add / edit / deactivate workers and categories
- `/analytics` — counts by category, mean-time-to-resolve, top hot spots
- `/settings` — admin users, alert channel config

Key UX: the **Approve & Dispatch** button is the only place
`send_dispatch_to_worker` can be invoked. The button confirms with a modal
that shows the exact WhatsApp message that will be sent to the worker.

---

## 10. Repo layout

```
hbc_whatsapp_claw/
├── PLAN.md                              ← this document
├── README.md
├── docker-compose.yml                   ← postgres, minio (local), openclaw, skills, portal
├── .env.example
├── infra/
│   └── openclaw/
│       ├── config.yaml                  ← whatsapp channel, allowFrom, plugin hooks
│       ├── system_prompt.md             ← resident agent prompt (multilingual)
│       └── plugins/                     ← language_detect, media_handler, audit_logger…
├── services/
│   └── skills/                          ← Python FastAPI + FastMCP
│       ├── pyproject.toml
│       ├── src/society_skills/
│       │   ├── main.py                  ← entrypoint: starts MCP stdio + HTTP API
│       │   ├── mcp_tools.py             ← @mcp.tool decorators
│       │   ├── http_api.py              ← FastAPI for admin portal
│       │   ├── db.py                    ← SQLAlchemy / asyncpg
│       │   ├── storage.py               ← R2 client + presigned URLs
│       │   ├── llm.py                   ← Claude API wrapper (caching + retries)
│       │   ├── classifier.py            ← classify_severity implementation
│       │   ├── dispatch.py              ← send_dispatch_to_worker, OpenCLAW outbound bridge
│       │   ├── models.py                ← Pydantic + ORM
│       │   └── settings.py              ← env-driven config
│       └── tests/
├── db/
│   └── migrations/                      ← Alembic
└── apps/
    └── admin-portal/                    ← Next.js 15 App Router
        ├── package.json
        ├── src/
        │   ├── app/
        │   │   ├── (auth)/login/
        │   │   ├── queue/
        │   │   ├── tickets/[id]/
        │   │   ├── residents/
        │   │   ├── workers/
        │   │   └── analytics/
        │   ├── server/
        │   │   ├── trpc/
        │   │   └── api/                 ← thin proxy to services/skills HTTP
        │   └── components/
        └── prisma/schema.prisma         ← read-only mirror of db/migrations
```

---

## 11. Phased milestones

### M0 — Bootstrap (1–2 days)
- Repo skeleton, docker-compose with Postgres + MinIO.
- Alembic migrations for the schema in §5.
- Self-hosted OpenCLAW container talking to a throwaway WhatsApp number.
- Skill server exposing a single `ping` MCP tool to prove the wire works.

### M1 — Resident reporting (4–6 days)
- Skills: `register_or_get_resident`, `update_resident_profile`,
  `create_complaint`, `classify_severity`, `attach_media`.
- Plugins: `language_detect`, `media_handler`, `audit_logger`.
- System prompt + multilingual flow.
- End-to-end: a resident can DM the bot, onboard, send a voice/photo
  complaint, and get a ticket number back.

### M2 — Admin portal (4–6 days)
- Next.js scaffold + auth.
- `/queue`, `/tickets/[id]`, `/residents`, `/workers`.
- HTTP API on skills service for portal reads.
- Photo viewer via pre-signed R2 URLs.

### M3 — Dispatch + critical alerts (3–4 days)
- `send_dispatch_to_worker` skill, gated behind portal approval.
- `escalate_to_admin` + `critical_alert_router` plugin.
- `worker_status_router` plugin + worker reply flow (ACCEPT / DONE / HELP).
- Resident rating + reopen flow.

### M4 — Hardening (ongoing)
- SLA escalations (auto-bump severity if open >24h).
- Reminders for in-progress tasks.
- Analytics dashboard.
- Migration path notes from Baileys → WhatsApp Business API.

---

## 12. Open questions for the user

These don't block M0/M1 but I'd like answers before M2/M3:

1. **Auth for admins:** Clerk (managed, ~10 min to set up) or NextAuth credentials (self-hosted, no third-party)?
2. **Hosting:** Hetzner/DO VPS for pilot, or do you already have infra?
3. **WhatsApp number:** Do you have a dedicated SIM for the bot? Baileys ties the session to one number.
4. **Admin alert channel:** A dedicated WhatsApp group with all admins, or DM each admin individually?
5. **Worker onboarding:** Will admins type worker phone numbers in the portal, or do workers register themselves by messaging the bot first?
6. **Resident verification:** Should we ask the society office to import a residents list (CSV), or trust self-declared tower/flat?
7. **Regional languages beyond Hindi/English:** Which ones specifically? (Marathi/Tamil/Telugu/Kannada all need explicit Claude system-prompt examples for best results.)

---

## 13. Risks & how we'll handle them

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Baileys session drops / WhatsApp bans the number | Medium | High | Use a dedicated SIM, never the founder's number; backup credentials nightly; have a documented re-pairing playbook; plan WABA migration. |
| Voice transcription gets Hindi wrong | High at first | Medium | Agent always echoes the parsed intent and asks "Sahi samjha?" before opening a ticket. |
| Hallucinated worker dispatch | Low (we gate it) | Critical | `send_dispatch_to_worker` is not in the agent's tool list — only the portal API path can call it. |
| Spam / non-resident messaging the bot | Medium | Low | `dmPolicy` to require allowlist OR a "verify with society code" onboarding step before any ticket is created. |
| Privacy: photos may include faces / vehicle plates | Medium | Medium | Photos stored in private R2 bucket, signed URLs expire in 15 min, admin portal shows them only inside an audited iframe; retention policy of 90 days post-resolution. |
| LLM cost spikes | Low | Medium | Haiku for the per-message classifier; Sonnet only when the agent is in active dialog; prompt-cache the system prompt + worker/category catalog. |

---

## 14. What I'll build first (proposed)

If you say "go", I'll start with **M0 + M1** in this order:

1. Repo skeleton, `docker-compose.yml`, `.env.example`.
2. Postgres schema + Alembic migration #001 (tables in §5).
3. `services/skills` Python project with: `ping` MCP tool, DB connection,
   `register_or_get_resident`, `create_complaint`, `classify_severity`.
4. OpenCLAW config: WhatsApp channel + plugin hooks (`language_detect`,
   `audit_logger`).
5. System prompt for the resident agent (English + Hindi + Hinglish).
6. A test harness that simulates an inbound WhatsApp message end-to-end
   without needing a real phone, so we can iterate fast.

Sources used while drafting this plan:

- [OpenCLAW WhatsApp channel docs](https://docs.openclaw.ai/channels/whatsapp)
- [OpenCLAW Skills docs](https://docs.openclaw.ai/tools/skills)
- [OpenCLAW Plugin bundles](https://docs.openclaw.ai/plugins/bundles)
- [OpenCLAW MCP overview](https://docs.openclaw.ai/cli/mcp)
