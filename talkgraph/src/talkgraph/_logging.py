"""Tiny logging setup.

Single entry point — `setup_logging(level)` — called from the FastAPI
lifespan and (optionally) from CLI scripts that want to surface library
diagnostics. Idempotent: re-invocation replaces talkgraph-owned handlers
without affecting handlers other libraries may have installed.

No JSON formatter, no per-request IDs, no rotation. Add those when there's
a real aggregator to feed; until then, plain text on stderr is fine.
"""

from __future__ import annotations

import logging
import sys

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_SENTINEL_ATTR = "_talkgraph_owned"


def setup_logging(level: str | int = "INFO") -> None:
    root = logging.getLogger()
    # Idempotency: drop only the handlers we previously installed; leave any
    # other library's handlers (or test fixtures' handlers) untouched.
    for h in list(root.handlers):
        if getattr(h, _SENTINEL_ATTR, False):
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    setattr(handler, _SENTINEL_ATTR, True)
    root.addHandler(handler)

    root.setLevel(level)

    # Tame chatty libraries — these emit INFO-level lines per request that
    # drown out our own diagnostics.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # neo4j-driver routes notifications here; T8 disables DEPRECATIONS at the
    # driver, but everything else still flows through this logger.
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
