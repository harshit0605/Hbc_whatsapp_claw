"""Pytest fixtures. Uses real Postgres via DATABASE_URL — run inside
docker-compose or against a local Postgres pointed at by env vars."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text

from society_skills.db import close_engine, session_scope


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Wipe tables between tests."""
    if not os.getenv("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("DATABASE_URL not set; integration tests skipped")
    async with session_scope() as s:
        for tbl in [
            "rating",
            "message_log",
            "assignment",
            "complaint_media",
            "complaint",
            "resident_flat",
            "resident",
            "flat",
            "tower",
            "worker",
            "admin_user",
        ]:
            await s.execute(text(f"truncate table {tbl} restart identity cascade"))
    yield
    await close_engine()
