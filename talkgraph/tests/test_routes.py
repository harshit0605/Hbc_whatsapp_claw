"""HTTP-layer tests for the FastAPI routes.

Builds a small app that mounts the router with a stubbed app.state.graph,
then drives it with httpx.AsyncClient + ASGITransport so no real Neo4j or
network round-trip is involved.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from talkgraph.api.routes import router


class _GraphStub:
    """Minimal stand-in for Neo4jGraphStore — async methods only matter for
    the endpoints we actually hit in a given test."""

    def __init__(self, *, verify_raises: Exception | None = None):
        self._verify_raises = verify_raises

    async def verify(self) -> None:
        if self._verify_raises:
            raise self._verify_raises


def _app_with(graph) -> FastAPI:
    app = FastAPI()
    app.state.graph = graph
    app.include_router(router)
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
