"""End-to-end resident reporting flow against the MCP handlers,
simulating what OpenCLAW would invoke."""
from __future__ import annotations

import json

import pytest

from society_skills import mcp_tools


async def _call(name: str, **args):
    handler = mcp_tools._HANDLERS[name]
    return await handler(args)


@pytest.mark.asyncio
async def test_first_message_creates_pending_resident():
    out = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    data = json.loads(out.model_dump_json())
    assert data["is_new"] is True
    assert data["resident"]["status"] == "pending"

    again = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    assert json.loads(again.model_dump_json())["is_new"] is False


@pytest.mark.asyncio
async def test_full_onboarding_and_complaint():
    out = await _call(
        "register_or_get_resident",
        wa_jid="9198xxxxxxxx@s.whatsapp.net",
        display_name="Rohit Sharma",
    )
    rid = json.loads(out.model_dump_json())["resident"]["id"]

    await _call(
        "update_resident_profile",
        resident_id=rid,
        tower_name="Tower B",
        flat_number="1804",
        language="hi",
        status="verified",
    )

    cls = await _call(
        "classify_complaint",
        text="kitchen sink leak ho raha hai",
    )
    cls_d = json.loads(cls.model_dump_json())
    assert cls_d["category"] in ("plumbing", "water", "other")
    assert cls_d["severity"] in ("low", "medium", "high", "critical")

    res = await _call(
        "create_complaint",
        resident_id=rid,
        category=cls_d["category"],
        severity=cls_d["severity"],
        title=cls_d["title"],
        description="kitchen sink leak ho raha hai",
    )
    assert res["complaint"]["ticket_no"] >= 1
    assert res["complaint"]["tower_name"] == "Tower B"
    assert res["complaint"]["flat_number"] == "1804"
    assert res["is_critical"] is False


@pytest.mark.asyncio
async def test_critical_classification_flags():
    cls = await _call(
        "classify_complaint",
        text="gas leak in Tower A flat 502, smell is very strong",
    )
    d = json.loads(cls.model_dump_json())
    assert d["severity"] == "critical"
    assert d["category"] in ("gas", "security", "other")


@pytest.mark.asyncio
async def test_worker_lifecycle():
    # Register a resident + complaint
    out = await _call("register_or_get_resident", wa_jid="9198xxxxxxxx@s.whatsapp.net")
    rid = json.loads(out.model_dump_json())["resident"]["id"]
    res = await _call(
        "create_complaint",
        resident_id=rid,
        category="garbage",
        severity="medium",
        title="Overflowing dustbin",
        description="kachra do din se pada hai",
    )
    cid = res["complaint"]["id"]

    # Register a worker via the repo layer directly (HTTP route covers the public path)
    from uuid import UUID
    from society_skills import repo
    from society_skills.db import session_scope

    async with session_scope() as s:
        w = await repo.create_worker(
            s, phone="9198111111111", name="Ramesh", categories=["garbage", "cleanliness"],
            wa_jid="9198111111111@s.whatsapp.net",
        )
        await repo.create_assignment(
            s, complaint_id=UUID(cid), worker_id=w.id, approved_by=None
        )

    accept = await _call(
        "worker_status_update",
        worker_wa_jid="9198111111111@s.whatsapp.net",
        action="accept",
    )
    assert accept["action"] == "accept"

    done = await _call(
        "worker_status_update",
        worker_wa_jid="9198111111111@s.whatsapp.net",
        action="done",
    )
    assert done["action"] == "done"
