from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

router = APIRouter()


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


@router.get("/commitments")
async def list_commitments(request: Request, status: Optional[str] = "open"):
    return await request.app.state.graph.get_commitments(status=status)
