# Society Maintenance WhatsApp Bot

A WhatsApp-first maintenance assistant for residential societies, built on
[**OpenCLAW**](https://docs.openclaw.ai) (Baileys WhatsApp channel + MCP skills) and
[Claude](https://www.anthropic.com/api). Residents report issues in plain
language (text / voice / photo) in English, Hindi, or regional languages.
Admins triage from a web portal and dispatch tasks to workers via WhatsApp
after explicit human approval.

See [`PLAN.md`](./PLAN.md) for the full design.

---

## Stack at a glance

| Layer | What |
|---|---|
| Agent runtime | OpenCLAW (`infra/openclaw/`) |
| Skills (MCP) + HTTP API | Python / FastMCP + FastAPI (`services/skills/`) |
| Database | PostgreSQL 16 |
| Media storage | S3-compatible (MinIO locally, R2/S3 in prod) |
| Admin portal | Next.js 15 + Tailwind (`apps/admin-portal/`) |
| LLM | Claude Sonnet 4.6 (conversation) + Haiku 4.5 (classifier) |

## Quick start (local)

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY at minimum. Everything else has sane dev defaults.

docker compose up --build
# wait for skills-migrate to complete the schema, then…
# - Admin portal at http://localhost:3000 (bootstrap admin from BOOTSTRAP_ADMIN_*)
# - MinIO console at http://localhost:9001 (login from .env)
# - OpenCLAW container logs will show a WhatsApp Web QR code on first run.
#   Scan it from the dedicated WhatsApp account to pair.
```

## End-to-end without WhatsApp

You don't need a real phone to test the skills + portal. Use the simulator:

```bash
# In another shell with the stack running:
python scripts/simulate_inbound.py \
  --jid 9198xxxxxxxx@s.whatsapp.net \
  --name "Rohit Sharma" \
  --tower "Tower B" --flat 1804 \
  --message "kitchen sink leak ho raha hai" \
  --image path/to/leak.jpg
```

This drives the same MCP tools OpenCLAW would invoke, so you can watch the
ticket appear in the admin portal at `http://localhost:3000/queue`.

## Repo layout

```
PLAN.md                              ← architecture + milestones
docker-compose.yml
infra/openclaw/                      ← agent config, prompt, plugins, Dockerfile
services/skills/                     ← Python: MCP tools + FastAPI + Alembic migrations
apps/admin-portal/                   ← Next.js admin portal
scripts/                             ← simulators, smoke tests
```

## Tests

```bash
cd services/skills
pip install -e .[dev]
# Requires Postgres on localhost (or set DATABASE_URL).
pytest
```

## Operational notes

- **WhatsApp account**: use a dedicated SIM, not the founder's number. Baileys
  sessions are tied to a single WhatsApp account.
- **Dispatch gate**: dispatch is exposed only on the HTTP API
  (`POST /complaints/{id}/dispatch`) — the agent's MCP tool catalog
  deliberately omits it, so the agent cannot dispatch on its own.
- **Critical alerts**: set `ADMIN_ALERT_JIDS` to a comma-separated list of
  WhatsApp JIDs (or a group JID). Critical complaints auto-escalate from
  inside `create_complaint` — no reliance on the agent remembering to call
  `escalate_to_admin`.
- **Voice notes**: `/transcribe` returns 501 by default. Set
  `STT_PROVIDER_URL` to a Whisper-compatible endpoint to enable. Without it,
  voice notes are still stored but the agent only sees the audio token.
- **Token rotation**: the shared bearer (`SKILLS_API_TOKEN`) is used by the
  admin portal, every OpenCLAW plugin, and the skills service. Rotate all
  three together.
- **Backups**: nightly `pg_dump` + nightly snapshot of
  `/data/credentials` (Baileys session) is recommended.

## What v1 ships

| Capability | Status |
|---|---|
| Resident onboarding (text/voice/photo, multi-language) | ✅ |
| LLM classification + severity tagging (Claude + heuristic fallback) | ✅ |
| Critical-issue auto-escalation to admin WhatsApp | ✅ |
| Admin web portal: queue, ticket detail, residents, workers, analytics, settings | ✅ |
| Human-gated worker dispatch with confirmation modal | ✅ |
| Worker ACCEPT / DONE / HELP loop, resident status notifications, rating prompt | ✅ |
| Server-ranked worker suggestions (category match + open load) | ✅ |
| Audit log of every inbound/outbound WhatsApp message | ✅ |
| Voice transcription wiring (proxy to your STT provider) | ✅ (pluggable) |
| Baileys allowlist sync, SLA escalation jobs, photo retention policy, audit-iframe viewer | M4 |
