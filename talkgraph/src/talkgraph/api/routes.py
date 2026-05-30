from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request):
    """Readiness probe: 200 when Neo4j responds, 503 otherwise.

    The simpler /health (in main.py) is the liveness probe and doesn't touch
    any dependency — process up == 200. /healthz is the readiness probe and
    is what an orchestrator (k8s, ECS, etc.) should gate traffic on.
    """
    try:
        await request.app.state.graph.verify()
    except Exception as e:  # noqa: BLE001 — any failure means not-ready
        raise HTTPException(status_code=503, detail=f"neo4j unreachable: {e}")
    return {"status": "ready"}


@router.post("/conversations")
async def create_conversation(
    request: Request,
    file: UploadFile = File(...),
    date: Optional[str] = None,
):
    state = request.app.state
    audio_path = await state.storage.save_audio(file)
    result = await state.orchestrator.process_audio(audio_path, source="upload", date=date)
    state.storage.save_transcript(result.conversation_id, result.transcript)
    return {"conversation_id": result.conversation_id, "insights": result.insights}


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    data = await request.app.state.graph.get_conversation(conversation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return data


@router.get("/people/{name}")
async def get_person(request: Request, name: str):
    data = await request.app.state.graph.get_person_view(name)
    if data is None:
        raise HTTPException(status_code=404, detail="person not found")
    return data


@router.get("/people/{name}/commitments")
async def get_person_commitments(
    request: Request, name: str, status: Optional[str] = "open"
):
    data = await request.app.state.graph.get_person_commitments(name, status=status)
    if data is None:
        raise HTTPException(status_code=404, detail="person not found")
    return data


@router.get("/people/{name_a}/with/{name_b}")
async def get_dyad(request: Request, name_a: str, name_b: str):
    try:
        data = await request.app.state.graph.get_dyad_view(name_a, name_b)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="one or both people not found")
    return data


@router.get("/commitments")
async def list_commitments(request: Request, status: Optional[str] = "open"):
    return await request.app.state.graph.get_commitments(status=status)


@router.get("/topics")
async def list_topics(request: Request, limit: int = 50):
    return await request.app.state.graph.list_topics(limit=limit)


@router.get("/topics/{name}/related")
async def get_related_topics(request: Request, name: str, limit: int = 20):
    data = await request.app.state.graph.get_related_topics(name, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return data


@router.get("/topics/{name}")
async def get_topic(request: Request, name: str):
    data = await request.app.state.graph.get_topic_view(name)
    if data is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return data
