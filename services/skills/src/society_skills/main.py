"""Entry point. Supports two modes:

  python -m society_skills.main http   → run the FastAPI HTTP API
  python -m society_skills.main mcp    → run the MCP stdio server (used by OpenCLAW)
"""
from __future__ import annotations

import asyncio
import sys

import uvicorn

from .logging_setup import configure_logging
from .settings import get_settings


def _run_http() -> None:
    configure_logging()
    s = get_settings()
    uvicorn.run(
        "society_skills.http_api:app",
        host=s.skills_http_host,
        port=s.skills_http_port,
        log_config=None,
        access_log=False,
    )


def _run_mcp() -> None:
    configure_logging()
    from .mcp_tools import serve_stdio

    asyncio.run(serve_stdio())


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "http"
    if mode == "http":
        _run_http()
    elif mode == "mcp":
        _run_mcp()
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
