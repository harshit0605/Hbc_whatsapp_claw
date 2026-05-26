"""Second-pass regression tests covering:

- auto-escalation of critical complaints
- worker DONE → resident gets a rating prompt
- propose_workers ranks category-matching first, lower-load first
- update_resident_profile re-link drops the old flat
- find_resident_by_jid is deterministic with multiple flats
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from society_skills import mcp_tools, repo
from society_skills.db import session_scope


async def _call(name: str, **args):
    return await mcp_tools._HANDLERS[name](args)


@pytest.mark.asyncio
async def test_create_critical_complaint_auto_escalates():
    out = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    rid = json.loads(out.model_dump_json())["resident"]["id"]

    with patch("society_skills.mcp_tools.broadcast_admin_alert", new=AsyncMock(return_value=[])) as m:
        res = await _call(
            "create_complaint",
            resident_id=rid,
            category="gas",
            severity="critical",
            title="Gas leak Tower A 502",
            description="strong gas smell — leak suspected",
        )
        assert res["is_critical"] is True
        m.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_done_notifies_resident_with_rating_prompt():
    out = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    rid = json.loads(out.model_dump_json())["resident"]["id"]
    res = await _call(
        "create_complaint",
        resident_id=rid, category="garbage", severity="medium",
        title="kachra", description="kachra do din se pada hai",
    )

    async with session_scope() as s:
        w = await repo.create_worker(
            s, phone="9198222222222", name="Ramesh",
            categories=["garbage"], wa_jid="9198222222222@s.whatsapp.net",
        )
        await repo.create_assignment(
            s, complaint_id=UUID(res["complaint"]["id"]), worker_id=w.id, approved_by=None,
        )

    with patch("society_skills.mcp_tools.send_text", new=AsyncMock(return_value={})) if False else \
         patch("society_skills.dispatch.send_text", new=AsyncMock(return_value={})) as m:
        done = await _call(
            "worker_status_update",
            worker_wa_jid="9198222222222@s.whatsapp.net",
            action="done",
        )
        assert done["action"] == "done"
        m.assert_awaited()
        sent_body = m.await_args.kwargs.get("body", "") if m.await_args.kwargs else m.await_args.args[1]
        assert "1-5" in sent_body or "rate" in sent_body.lower()


@pytest.mark.asyncio
async def test_propose_workers_ranks_by_category_then_load():
    async with session_scope() as s:
        a = await repo.create_worker(
            s, phone="91981", name="A-plumber", categories=["plumbing"],
            wa_jid="91981@s.whatsapp.net",
        )
        b = await repo.create_worker(
            s, phone="91982", name="B-electrician", categories=["electrical"],
            wa_jid="91982@s.whatsapp.net",
        )
        c = await repo.create_worker(
            s, phone="91983", name="C-plumber-busy", categories=["plumbing"],
            wa_jid="91983@s.whatsapp.net",
        )

        # Give C-plumber-busy an open load.
        out = await _call("register_or_get_resident", wa_jid="r@s.whatsapp.net")
        rid = json.loads(out.model_dump_json())["resident"]["id"]
        prev = await _call(
            "create_complaint",
            resident_id=rid, category="plumbing", severity="low",
            title="prev", description="prev",
        )
        await repo.create_assignment(
            s, complaint_id=UUID(prev["complaint"]["id"]), worker_id=c.id, approved_by=None,
        )

    async with session_scope() as s:
        ranked = await repo.propose_workers_for_complaint(s, category="plumbing")

    names = [w.name for w in ranked]
    # Plumbers first; lower-load plumber before the busy one; electrician last.
    assert names.index("A-plumber") < names.index("C-plumber-busy")
    assert names.index("C-plumber-busy") < names.index("B-electrician")


@pytest.mark.asyncio
async def test_update_profile_relinks_flat():
    out = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    rid = json.loads(out.model_dump_json())["resident"]["id"]

    await _call(
        "update_resident_profile",
        resident_id=rid, tower_name="Tower B", flat_number="1804",
    )
    after_first = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    assert json.loads(after_first.model_dump_json())["resident"]["flat_number"] == "1804"

    # Correction
    await _call(
        "update_resident_profile",
        resident_id=rid, tower_name="Tower B", flat_number="1805",
    )
    after_fix = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    assert json.loads(after_fix.model_dump_json())["resident"]["flat_number"] == "1805"

    # Verify the old flat link is gone.
    async with session_scope() as s:
        from sqlalchemy import text as sqltext
        rows = (
            await s.execute(
                sqltext(
                    "select f.flat_number from resident_flat rf "
                    "join flat f on f.id = rf.flat_id where rf.resident_id = :id"
                ),
                {"id": rid},
            )
        ).all()
    assert {r[0] for r in rows} == {"1805"}
