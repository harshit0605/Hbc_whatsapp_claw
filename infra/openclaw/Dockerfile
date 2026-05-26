# OpenCLAW gateway image.
#
# The exact OpenCLAW base image / CLI install instructions evolve with
# upstream releases. This Dockerfile pins to the latest stable installer
# pattern from the OpenCLAW docs. If you self-host a different version,
# adjust the install command — everything else (config + plugins) is stable.

FROM python:3.12-slim

WORKDIR /openclaw

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

# Install OpenCLAW CLI. Pin a version once you're past the pilot.
RUN curl -fsSL https://install.openclaw.ai | sh -s -- --yes \
  || echo "openclaw installer placeholder — replace with your pinned install"

# Plugin runtime deps.
COPY plugins/ ./plugins/
RUN pip install --no-cache-dir httpx langdetect

# Mount points (also declared as volumes in docker-compose):
#   /openclaw/config.yaml   ← config
#   /data/credentials       ← Baileys session
VOLUME ["/data/credentials"]

EXPOSE 7787

# `openclaw start` reads config.yaml from CWD and serves on $PORT (default 7787
# for the outbound HTTP plugin).
CMD ["openclaw", "start", "--config", "/openclaw/config.yaml"]
