"""Ingest a WhatsApp-exported voice note (or any audio file) end-to-end.

This bootstraps the WhatsApp capture loop WITHOUT a live wire: export /
forward a voice note out of WhatsApp, drop the file in a folder, and this
script runs the real transcribe → diarize → extract → graph pipeline on it.

Same pipeline run_sample.py exercises, plus:
  - batch mode (--dir),
  - watch mode (--watch) that polls a folder and ingests new files only,
  - friendlier per-file summary,
  - per-file error isolation (one bad file doesn't kill the run).

Note: §4 of CONTINUATION.md says the real-audio path has never been
verified. This script is the first thing that does. Watch for failures
in Whisper or the structured-output extractor on actual voice notes.

Examples:
    # Single file
    python scripts/ingest_voice_note.py ~/Downloads/voice-2026-05-28.opus

    # A whole folder of exports
    python scripts/ingest_voice_note.py --dir ~/Downloads/whatsapp_exports/

    # Watch a folder, ingest new files as they appear (Ctrl-C to stop)
    python scripts/ingest_voice_note.py --watch ~/Downloads/whatsapp_exports/

    # Just transcribe + extract; don't touch Neo4j
    python scripts/ingest_voice_note.py voice.opus --no-graph
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable

from openai import AsyncOpenAI

from talkgraph.graph.store import Neo4jGraphStore
from talkgraph.pipeline.diarize import LLMDiarizer
from talkgraph.pipeline.extract import OpenAIInsightExtractor
from talkgraph.pipeline.orchestrator import Orchestrator
from talkgraph.pipeline.transcribe import OpenAISTTProvider
from talkgraph.settings import get_settings

# Whisper accepts opus / ogg / m4a / mp3 / wav / webm / mp4 / mpeg / flac
# directly. WhatsApp exports voice notes as .opus (or .ogg inside .zip).
_AUDIO_EXTS = {".opus", ".ogg", ".m4a", ".mp3", ".wav", ".webm", ".mp4", ".mpeg", ".flac"}


class _NullGraph:
    async def ingest_conversation(self, **_):
        return None


def _gather_files(targets: Iterable[Path]) -> list[Path]:
    """Expand a mixed list of file/dir paths to audio files only.

    Directories are walked one level (non-recursive) to avoid sucking in old
    archives. Unknown-extension entries are reported and skipped, not failed.
    """
    out: list[Path] = []
    seen: set[Path] = set()
    for t in targets:
        if t.is_dir():
            for p in sorted(t.iterdir()):
                if p.is_file() and p.suffix.lower() in _AUDIO_EXTS and p not in seen:
                    out.append(p)
                    seen.add(p)
        elif t.is_file():
            if t.suffix.lower() in _AUDIO_EXTS and t not in seen:
                out.append(t)
                seen.add(t)
            else:
                print(f"[skip] {t}: not a recognised audio extension")
        else:
            print(f"[skip] {t}: not found")
    return out


def _summarize(path: Path, result) -> str:
    insights = result.insights
    lines = [
        f"[OK] {path.name}",
        f"     id:      {result.conversation_id}",
        f"     title:   {insights.title}",
    ]
    if insights.summary:
        s = insights.summary
        lines.append(f"     summary: {s[:120]}{'…' if len(s) > 120 else ''}")
    if insights.participants:
        lines.append(f"     people:  {', '.join(insights.participants)}")
    if insights.commitments:
        n = len(insights.commitments)
        preview = ", ".join(c.text for c in insights.commitments[:2])
        more = "…" if n > 2 else ""
        lines.append(f"     commits: {n} ({preview}{more})")
    return "\n".join(lines)


def _build_orchestrator(no_graph: bool):
    settings = get_settings()
    key = settings.openai_api_key
    # The fixture demo uses an "offline-placeholder" key; the placeholder in
    # .env.example is "sk-..." — both are recognisable. We need a real key.
    if not key or key.startswith("sk-...") or key == "offline-placeholder":
        raise SystemExit(
            "OPENAI_API_KEY is not set to a real key in .env. Real-audio "
            "ingestion needs a live key (Whisper + GPT-4o)."
        )
    client = AsyncOpenAI(api_key=key)
    graph = (
        _NullGraph()
        if no_graph
        else Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    )
    orchestrator = Orchestrator(
        stt=OpenAISTTProvider(client, settings.openai_stt_model),
        diarizer=LLMDiarizer(client, settings.openai_diarize_model),
        extractor=OpenAIInsightExtractor(client, settings.openai_extract_model),
        graph=graph,
    )
    return client, graph, orchestrator


async def _ingest_one(path: Path, orchestrator, date: str | None = None) -> bool:
    try:
        result = await orchestrator.process_audio(
            str(path), source="whatsapp-bootstrap", date=date
        )
    except Exception as e:
        # Per-file isolation: one corrupt voice note shouldn't kill the run.
        print(f"[ERR] {path.name}: {type(e).__name__}: {e}")
        return False
    print(_summarize(path, result))
    return True


def _load_seen(seen_path: Path) -> set[str]:
    if not seen_path.exists():
        return set()
    try:
        return set(json.loads(seen_path.read_text()))
    except (ValueError, OSError):
        return set()


def _save_seen(seen_path: Path, seen: set[str]) -> None:
    try:
        seen_path.write_text(json.dumps(sorted(seen)))
    except OSError as e:
        # Worst case we re-ingest on next run — log and continue.
        print(f"[warn] couldn't persist seen-set to {seen_path}: {e}")


async def _watch(folder: Path, orchestrator, interval: float) -> None:
    seen_path = folder / ".talkgraph_seen"
    seen = _load_seen(seen_path)
    print(f"[watch] {folder} (every {interval}s; {len(seen)} already-seen, Ctrl-C to stop)")
    try:
        while True:
            new_files = [
                p
                for p in sorted(folder.iterdir())
                if p.is_file()
                and p.suffix.lower() in _AUDIO_EXTS
                and p.name not in seen
            ]
            for p in new_files:
                if await _ingest_one(p, orchestrator):
                    seen.add(p.name)
                    _save_seen(seen_path, seen)
            await asyncio.sleep(interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[watch] stopped")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="*", type=Path, help="audio files to ingest")
    parser.add_argument(
        "--dir", type=Path, action="append", default=[], help="directory of audio files (repeatable)"
    )
    parser.add_argument(
        "--watch", type=Path, help="poll this directory for new audio files and ingest them"
    )
    parser.add_argument("--no-graph", action="store_true", help="skip Neo4j ingest")
    parser.add_argument("--date", help="ISO date override (single-file / batch only)")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="watch poll interval, seconds (default 5)"
    )
    args = parser.parse_args()

    if args.watch and (args.files or args.dir):
        parser.error("--watch is exclusive with positional files / --dir")
    if not args.watch and not args.files and not args.dir:
        parser.error("provide files, --dir, or --watch")

    client, graph, orchestrator = _build_orchestrator(args.no_graph)
    if not args.no_graph:
        await graph.verify()
        await graph.ensure_constraints()

    try:
        if args.watch:
            if not args.watch.is_dir():
                raise SystemExit(f"--watch path is not a directory: {args.watch}")
            await _watch(args.watch, orchestrator, args.interval)
        else:
            files = _gather_files(list(args.files) + list(args.dir))
            if not files:
                print("[warn] no audio files found in the given targets")
            for p in files:
                await _ingest_one(p, orchestrator, date=args.date)
    finally:
        if not args.no_graph:
            await graph.close()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
