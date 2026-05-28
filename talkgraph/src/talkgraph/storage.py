import os
import uuid

from .models import Transcript


class LocalStorage:
    """Filesystem store for uploaded audio and transcript artifacts (dev/MVP)."""

    def __init__(self, base_dir: str):
        self.base = base_dir
        self.audio_dir = os.path.join(base_dir, "audio")
        self.transcript_dir = os.path.join(base_dir, "transcripts")
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.transcript_dir, exist_ok=True)

    async def save_audio(self, upload) -> str:
        ext = os.path.splitext(upload.filename or "")[1] or ".bin"
        path = os.path.join(self.audio_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            while chunk := await upload.read(1024 * 1024):
                out.write(chunk)
        return path

    def save_transcript(self, conversation_id: str, transcript: Transcript) -> str:
        path = os.path.join(self.transcript_dir, f"{conversation_id}.json")
        with open(path, "w", encoding="utf-8") as out:
            out.write(transcript.model_dump_json(indent=2))
        return path
