from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from openai import AsyncOpenAI

from ._logging import setup_logging
from .api.auth import require_api_token
from .api.routes import router
from .graph.store import Neo4jGraphStore
from .pipeline.diarize import LLMDiarizer
from .pipeline.extract import OpenAIInsightExtractor
from .pipeline.orchestrator import Orchestrator
from .pipeline.transcribe import OpenAISTTProvider
from .settings import get_settings
from .storage import LocalStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)
    log.info("talkgraph starting (neo4j=%s, auth=%s)", settings.neo4j_uri, "on" if settings.api_token else "off")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    graph = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    await graph.verify()
    await graph.ensure_constraints()
    log.info("neo4j reachable, constraints ensured")

    app.state.storage = LocalStorage(settings.data_dir)
    app.state.graph = graph
    app.state.orchestrator = Orchestrator(
        stt=OpenAISTTProvider(client, settings.openai_stt_model),
        diarizer=LLMDiarizer(client, settings.openai_diarize_model),
        extractor=OpenAIInsightExtractor(client, settings.openai_extract_model),
        graph=graph,
    )
    try:
        yield
    finally:
        log.info("talkgraph shutting down")
        await graph.close()
        await client.close()


app = FastAPI(title="talkgraph", version="0.1.0", lifespan=lifespan)
# Bearer auth is enforced at the router level. require_api_token short-circuits
# on /health and /healthz so probes still work without credentials.
app.include_router(router, dependencies=[Depends(require_api_token)])


@app.get("/health")
async def health():
    return {"status": "ok"}
