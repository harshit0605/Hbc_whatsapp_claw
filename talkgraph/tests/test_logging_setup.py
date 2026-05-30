"""setup_logging() is called from the FastAPI lifespan. Two things matter for
correctness: it must be idempotent (lifespan can be entered multiple times in
tests / reloads), and it must leave handlers other libraries / test fixtures
installed alone.
"""

from __future__ import annotations

import logging

from talkgraph._logging import setup_logging


def _talkgraph_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [h for h in root.handlers if getattr(h, "_talkgraph_owned", False)]


def _other_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [h for h in root.handlers if not getattr(h, "_talkgraph_owned", False)]


def test_setup_logging_adds_exactly_one_handler():
    root = logging.getLogger()
    pre = _other_handlers(root)

    setup_logging("INFO")
    assert len(_talkgraph_handlers(root)) == 1
    # Other handlers (pytest's, or any preset) are not removed.
    assert _other_handlers(root) == pre


def test_setup_logging_is_idempotent():
    """Calling twice should not double the handler count."""
    setup_logging("INFO")
    after_first = len(_talkgraph_handlers(logging.getLogger()))
    setup_logging("DEBUG")
    after_second = len(_talkgraph_handlers(logging.getLogger()))
    assert after_first == after_second == 1


def test_setup_logging_applies_level():
    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING

    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_tames_chatty_libraries():
    setup_logging("DEBUG")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("neo4j.notifications").level == logging.WARNING
