"""Bearer-token authentication for the talkgraph API.

Two-tier model:
  - When `Settings.api_token` is empty (the dev default), the dependency is a
    no-op — every request goes through. This keeps local development painless
    without env wrangling.
  - When set, every protected route requires `Authorization: Bearer <token>`.

The token is read through a tiny `get_api_token` sub-dependency so tests can
override it via `app.dependency_overrides` without fighting the lru_cache on
get_settings().

/healthz and /health are deliberately excluded — orchestrators need to probe
them without credentials.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from ..settings import get_settings

# Endpoints that must remain open even when api_token is set. /health lives
# directly on the FastAPI app (main.py); /healthz lives on the router but is
# the readiness probe and must be reachable for orchestrators.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/healthz"})


def get_api_token() -> str:
    """Dependency hook for tests to override the configured token."""
    return get_settings().api_token


async def require_api_token(
    request: Request,
    authorization: str | None = Header(default=None),
    expected: str = Depends(get_api_token),
) -> None:
    if request.url.path in _PUBLIC_PATHS:
        return
    if not expected:
        return  # dev mode: auth disabled
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid or missing api token")
