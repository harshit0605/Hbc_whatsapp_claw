# OpenCLAW gateway image.
#
# Build context must be the repo root (see docker-compose.yml). We:
#   1. Install the OpenCLAW CLI from upstream.
#   2. Install the skills service into the same image so the MCP stdio
#      server can be spawned by `python -m society_skills.main mcp`.
#   3. Drop in plugin runtime deps (httpx, langdetect).
#
# NOTE: The OpenCLAW upstream installer URL is intentionally a placeholder —
# pin to the install command from your OpenCLAW release. If you pull a
# prebuilt image instead (`FROM openclaw/openclaw:<tag>`), keep steps 2 + 3
# and skip the curl install.

FROM python:3.12-slim

WORKDIR /openclaw

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git build-essential libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# ─── 1. OpenCLAW CLI ─────────────────────────────────────────────────────
# Replace with your pinned installer command (or `FROM` an upstream image).
RUN curl -fsSL https://install.openclaw.ai | sh -s -- --yes \
 || (echo "ERROR: OpenCLAW installer failed. Pin a specific install command." \
     && exit 1)
ENV PATH="/root/.local/bin:/usr/local/bin:${PATH}"

# ─── 2. Skills service (so the MCP server can be spawned) ────────────────
COPY services/skills /app/services/skills
RUN pip install --upgrade pip \
 && pip install -e /app/services/skills

# Make the package importable for the MCP stdio entrypoint
ENV PYTHONPATH="/app/services/skills/src:${PYTHONPATH}"

# ─── 3. Plugin runtime deps ───────────────────────────────────────────────
COPY infra/openclaw/plugins/ /openclaw/plugins/
RUN pip install httpx langdetect

# Mount points (also declared as volumes in docker-compose):
#   /openclaw/config.yaml   ← config
#   /openclaw/system_prompt.md
#   /openclaw/plugins
#   /data/credentials       ← Baileys session
VOLUME ["/data/credentials"]

EXPOSE 7787

CMD ["openclaw", "start", "--config", "/openclaw/config.yaml"]
