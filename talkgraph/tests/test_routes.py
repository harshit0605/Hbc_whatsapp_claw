"""HTTP-layer tests for the FastAPI routes.

Builds a small app that mounts the router with a stubbed app.state.graph,
then drives it with httpx.AsyncClient + ASGITransport so no real Neo4j or
network round-trip is involved.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from talkgraph.api.auth import get_api_token, require_api_token
from talkgraph.api.routes import router


class _GraphStub:
    """Minimal stand-in for Neo4jGraphStore — async methods only matter for
    the endpoints we actually hit in a given test."""

    def __init__(self, *, verify_raises: Exception | None = None):
        self._verify_raises = verify_raises

    async def verify(self) -> None:
        if self._verify_raises:
            raise self._verify_raises

    async def get_commitments(self, status=None):
        return []  # used as a stand-in protected route in auth tests


def _app_with(graph, *, api_token: str | None = None) -> FastAPI:
    """Build the app. api_token=None → mount router without auth (the
    /healthz tests), api_token="" → mount with auth dependency in dev mode,
    api_token="secret" → mount with auth requiring that token.
    """
    app = FastAPI()
    app.state.graph = graph
    if api_token is None:
        app.include_router(router)
    else:
        app.include_router(router, dependencies=[Depends(require_api_token)])
        app.dependency_overrides[get_api_token] = lambda: api_token
    return app


async def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_healthz_returns_200_when_neo4j_reachable():
    app = _app_with(_GraphStub())
    async with await _client(app) as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


async def test_healthz_returns_503_when_neo4j_unreachable():
    app = _app_with(_GraphStub(verify_raises=ConnectionError("bolt: down")))
    async with await _client(app) as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 503
    body = resp.json()
    assert "neo4j unreachable" in body["detail"]
    assert "bolt: down" in body["detail"]


# --- Bearer auth ----------------------------------------------------------


async def test_auth_disabled_allows_unauthenticated_request():
    """api_token="" is the dev default — every request goes through."""
    app = _app_with(_GraphStub(), api_token="")
    async with await _client(app) as c:
        resp = await c.get("/commitments")
    assert resp.status_code == 200


async def test_auth_enabled_accepts_valid_bearer():
    app = _app_with(_GraphStub(), api_token="s3cret")
    async with await _client(app) as c:
        resp = await c.get("/commitments", headers={"Authorization": "Bearer s3cret"})
    assert resp.status_code == 200


async def test_auth_enabled_rejects_missing_header():
    app = _app_with(_GraphStub(), api_token="s3cret")
    async with await _client(app) as c:
        resp = await c.get("/commitments")
    assert resp.status_code == 401


async def test_auth_enabled_rejects_wrong_token():
    app = _app_with(_GraphStub(), api_token="s3cret")
    async with await _client(app) as c:
        resp = await c.get("/commitments", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_auth_enabled_rejects_wrong_scheme():
    """`Basic <creds>` shouldn't satisfy a Bearer requirement."""
    app = _app_with(_GraphStub(), api_token="s3cret")
    async with await _client(app) as c:
        resp = await c.get("/commitments", headers={"Authorization": "Basic s3cret"})
    assert resp.status_code == 401


async def test_healthz_remains_public_when_auth_enabled():
    """Orchestrators need to probe without credentials."""
    app = _app_with(_GraphStub(), api_token="s3cret")
    async with await _client(app) as c:
        resp = await c.get("/healthz")  # no Authorization header
    assert resp.status_code == 200
