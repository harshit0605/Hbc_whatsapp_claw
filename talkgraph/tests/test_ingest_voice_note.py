"""Hermetic tests for the pure helpers in scripts/ingest_voice_note.py.

The orchestrator path needs real OpenAI + Neo4j and isn't covered here; the
goal of this file is to lock down (a) which file extensions count as audio,
(b) directory walking is one level deep, (c) the per-file summary renders
cleanly when fields are missing or long.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ingest_voice_note as ivn
from talkgraph.models import Commitment, Insights, Quote, Transcript


def test_gather_files_filters_by_extension(tmp_path: Path):
    (tmp_path / "yes.opus").touch()
    (tmp_path / "yes.m4a").touch()
    (tmp_path / "yes.wav").touch()
    (tmp_path / "no.txt").touch()
    (tmp_path / "no.pdf").touch()

    files = ivn._gather_files([tmp_path])
    names = sorted(p.name for p in files)
    assert names == ["yes.m4a", "yes.opus", "yes.wav"]


def test_gather_files_is_not_recursive(tmp_path: Path):
    """Sub-folders are intentionally skipped — avoids sucking in old archives."""
    (tmp_path / "top.opus").touch()
    sub = tmp_path / "old"
    sub.mkdir()
    (sub / "buried.opus").touch()

    files = ivn._gather_files([tmp_path])
    assert [p.name for p in files] == ["top.opus"]


def test_gather_files_dedupes_when_dir_and_file_both_listed(tmp_path: Path):
    f = tmp_path / "voice.opus"
    f.touch()
    files = ivn._gather_files([tmp_path, f])
    assert files == [f]


def test_gather_files_skips_missing_and_wrong_extension(tmp_path: Path, capsys):
    missing = tmp_path / "ghost.opus"
    wrong = tmp_path / "notes.txt"
    wrong.touch()

    files = ivn._gather_files([missing, wrong])
    assert files == []
    out = capsys.readouterr().out
    assert "ghost.opus" in out
    assert "notes.txt" in out


@dataclass
class _FakeResult:
    conversation_id: str
    insights: Insights
    transcript: Transcript


def _result_with(**insight_overrides) -> _FakeResult:
    base = dict(
        title="Catch-up",
        summary="A short summary.",
        date=None,
        participants=["Alice", "Bob"],
        topics=["catch-up"],
        decisions=[],
        commitments=[
            Commitment(text="Send agenda", owner="Alice", due="Mon", status="open"),
            Commitment(text="Review draft", owner="Bob", due=None, status="open"),
            Commitment(text="Ship v2", owner="Alice", due=None, status="open"),
        ],
        action_items=[],
        notable_quotes=[Quote(speaker="Alice", quote="ok")],
    )
    base.update(insight_overrides)
    return _FakeResult(
        conversation_id="conv-123",
        insights=Insights(**base),
        transcript=Transcript(full_text="hi", segments=[]),
    )


def test_summarize_renders_all_fields():
    out = ivn._summarize(Path("voice.opus"), _result_with())
    assert "[OK] voice.opus" in out
    assert "conv-123" in out
    assert "Catch-up" in out
    assert "Alice, Bob" in out
    # commit preview shows first two + an ellipsis when there's a third
    assert "Send agenda, Review draft…" in out


def test_summarize_truncates_long_summary():
    long = "X" * 300
    out = ivn._summarize(Path("v.opus"), _result_with(summary=long))
    # 120 chars + ellipsis
    assert "X" * 120 + "…" in out
    assert "X" * 121 not in out


def test_summarize_omits_empty_sections():
    out = ivn._summarize(
        Path("v.opus"),
        _result_with(summary="", participants=[], commitments=[]),
    )
    assert "summary:" not in out
    assert "people:" not in out
    assert "commits:" not in out


def test_load_save_seen_roundtrip(tmp_path: Path):
    p = tmp_path / ".talkgraph_seen"
    assert ivn._load_seen(p) == set()
    ivn._save_seen(p, {"a.opus", "b.opus"})
    assert ivn._load_seen(p) == {"a.opus", "b.opus"}


def test_load_seen_handles_corrupt_file(tmp_path: Path):
    p = tmp_path / ".talkgraph_seen"
    p.write_text("not-json")
    assert ivn._load_seen(p) == set()
