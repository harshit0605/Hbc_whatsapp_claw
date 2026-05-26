"""MCP server exposing skills to the OpenCLAW agent over stdio."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import classifier, repo
from .db import session_scope
from .dispatch import broadcast_admin_alert
from .logging_setup import get_logger
from .models import RegisterResidentOut

log = get_logger("mcp")

server: Server = Server("society-skills")


# ─── Tool catalog ────────────────────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="propose_workers",
            description=(
                "Return up to 8 workers ranked by category match + current load + "
                "name. Use this BEFORE telling the resident an admin will assign — "
                "so you can mention realistic ETA."
            ),
            inputSchema={
                "type": "object",
                "required": ["complaint_id"],
                "properties": {"complaint_id": {"type": "string", "format": "uuid"}},
            },
        ),
        Tool(
            name="update_complaint_status",
            description=(
                "Change a complaint's status. Allowed transitions: open ↔ triaging, "
                "any → resolved/closed/rejected. Notifies the resident over WhatsApp."
            ),
            inputSchema={
                "type": "object",
                "required": ["complaint_id", "new_status"],
                "properties": {
                    "complaint_id": {"type": "string", "format": "uuid"},
                    "new_status": {
                        "type": "string",
                        "enum": [
                            "open", "triaging", "assigned", "in_progress",
                            "resolved", "closed", "rejected",
                        ],
                    },
                },
            },
        ),
        Tool(
            name="register_or_get_resident",
            description=(
                "Idempotently register a WhatsApp resident by their JID. If unknown, "
                "creates a pending stub. Always call this first when handling a "
                "resident message — it returns the current profile (tower, flat, "
                "language, status) which the agent uses to decide whether to onboard."
            ),
            inputSchema={
                "type": "object",
                "required": ["wa_jid"],
                "properties": {
                    "wa_jid": {"type": "string"},
                    "display_name": {"type": "string"},
                    "language": {
                        "type": "string",
                        "description": "ISO code: en, hi, mr, ta, te, kn",
                    },
                },
            },
        ),
        Tool(
            name="update_resident_profile",
            description="Fill in missing onboarding fields for a resident.",
            inputSchema={
                "type": "object",
                "required": ["resident_id"],
                "properties": {
                    "resident_id": {"type": "string", "format": "uuid"},
                    "display_name": {"type": "string"},
                    "language": {"type": "string"},
                    "tower_name": {"type": "string"},
                    "flat_number": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "verified", "blocked"],
                    },
                },
            },
        ),
        Tool(
            name="classify_complaint",
            description=(
                "Classify a complaint into category, severity, and short title. "
                "Pass the resident's text (already transcribed if it was voice) and "
                "any short descriptions of attached photos."
            ),
            inputSchema={
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "media_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        ),
        Tool(
            name="create_complaint",
            description=(
                "Create a complaint ticket. The agent should call classify_complaint "
                "first and pass the resulting category/severity/title here. Returns "
                "the new ticket including a human-friendly ticket_no."
            ),
            inputSchema={
                "type": "object",
                "required": ["resident_id", "category", "severity", "title", "description"],
                "properties": {
                    "resident_id": {"type": "string", "format": "uuid"},
                    "category": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "media_storage_keys": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["kind", "storage_key"],
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["image", "audio", "video", "document"],
                                },
                                "storage_key": {"type": "string"},
                                "mime": {"type": "string"},
                            },
                        },
                    },
                    "raw_input": {"type": "object"},
                },
            },
        ),
        Tool(
            name="escalate_to_admin",
            description=(
                "Send a critical-issue alert to the configured admin WhatsApp JIDs. "
                "Use this for life-safety scenarios: gas leak, fire, person trapped "
                "in lift, structural collapse, flooding."
            ),
            inputSchema={
                "type": "object",
                "required": ["complaint_id", "reason"],
                "properties": {
                    "complaint_id": {"type": "string", "format": "uuid"},
                    "reason": {"type": "string"},
                },
            },
        ),
        Tool(
            name="search_complaints",
            description="Look up complaints for the agent (e.g. resident asking for status).",
            inputSchema={
                "type": "object",
                "properties": {
                    "resident_id": {"type": "string", "format": "uuid"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        ),
        Tool(
            name="list_workers_by_category",
            description="List active workers for a category. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="record_resident_rating",
            description=(
                "Record a 1-5 rating from a resident on a completed complaint. "
                "If stars <= 2, reopens the ticket as 'open'."
            ),
            inputSchema={
                "type": "object",
                "required": ["complaint_id", "resident_id", "stars"],
                "properties": {
                    "complaint_id": {"type": "string", "format": "uuid"},
                    "resident_id": {"type": "string", "format": "uuid"},
                    "stars": {"type": "integer", "minimum": 1, "maximum": 5},
                    "comment": {"type": "string"},
                },
            },
        ),
        Tool(
            name="worker_status_update",
            description=(
                "Worker-channel: when a worker replies ACCEPT / DONE / HELP, update "
                "their current open assignment. Returns the affected complaint."
            ),
            inputSchema={
                "type": "object",
                "required": ["worker_wa_jid", "action"],
                "properties": {
                    "worker_wa_jid": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["accept", "done", "help", "cancel"],
                    },
                    "notes": {"type": "string"},
                },
            },
        ),
    ]


# ─── Dispatch table ──────────────────────────────────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return _text({"error": f"unknown tool: {name}"})
    try:
        result = await handler(arguments)
        return _text(result)
    except Exception as e:
        log.exception("mcp_tool_error", tool=name)
        return _text({"error": str(e)})


def _text(obj: Any) -> list[TextContent]:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return [TextContent(type="text", text=json.dumps(obj, default=str, ensure_ascii=False))]


# ─── Individual handlers ─────────────────────────────────────────────────────


async def _register_or_get_resident(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        resident, is_new = await repo.upsert_resident_stub(
            s,
            wa_jid=args["wa_jid"],
            display_name=args.get("display_name"),
            language=args.get("language"),
        )
        return RegisterResidentOut(resident=resident, is_new=is_new)


async def _update_resident_profile(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        return await repo.update_resident_profile(
            s,
            resident_id=UUID(args["resident_id"]),
            display_name=args.get("display_name"),
            language=args.get("language"),
            tower_name=args.get("tower_name"),
            flat_number=args.get("flat_number"),
            status=args.get("status"),
        )


async def _classify_complaint(args: dict[str, Any]) -> Any:
    return await classifier.classify(
        args["text"],
        media_descriptions=args.get("media_descriptions"),
    )


async def _create_complaint(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        resident_id = UUID(args["resident_id"])
        resident = await repo.get_resident_by_id(s, resident_id)
        tower_id = flat_id = None
        if resident and resident.tower_name and resident.flat_number:
            tower_id = await repo.ensure_tower(s, name=resident.tower_name)
            flat_id = await repo.ensure_flat(
                s, tower_id=tower_id, flat_number=resident.flat_number
            )

        media_keys: list[tuple[str, str, str | None]] = []
        for m in args.get("media_storage_keys") or []:
            media_keys.append((m["kind"], m["storage_key"], m.get("mime")))

        complaint = await repo.create_complaint(
            s,
            resident_id=resident_id,
            category=args["category"],
            severity=args["severity"],
            title=args["title"],
            description=args["description"],
            raw_input=args.get("raw_input"),
            tower_id=tower_id,
            flat_id=flat_id,
            media_keys=media_keys,
        )
    is_critical = complaint.severity == "critical"

    # Auto-escalate critical issues regardless of whether the agent remembers
    # to call escalate_to_admin. Belt-and-suspenders — life safety beats
    # prompt-engineering hopes.
    if is_critical:
        body = _format_admin_alert(complaint, reason="auto-escalated: severity=critical")
        try:
            await broadcast_admin_alert(body)
        except Exception as e:  # noqa: BLE001
            log.warning("auto_escalate_failed", complaint_id=str(complaint.id), error=str(e))

    return {"complaint": complaint.model_dump(mode="json"), "is_critical": is_critical}


async def _escalate_to_admin(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        complaint = await repo.get_complaint(s, complaint_id=UUID(args["complaint_id"]))
    if complaint is None:
        return {"error": "complaint not found"}

    body = _format_admin_alert(complaint, reason=args.get("reason", ""))
    results = await broadcast_admin_alert(body)
    return {"sent_to": results, "body": body}


def _format_admin_alert(complaint: Any, *, reason: str) -> str:
    loc = []
    if complaint.tower_name:
        loc.append(f"Tower {complaint.tower_name}")
    if complaint.flat_number:
        loc.append(f"Flat {complaint.flat_number}")
    where = ", ".join(loc) or "location unknown"
    contact = []
    if complaint.resident_name:
        contact.append(complaint.resident_name)
    if complaint.resident_phone:
        contact.append(f"+{complaint.resident_phone}")
    who = " / ".join(contact) or "unknown resident"
    return (
        f"🚨 CRITICAL #{complaint.ticket_no} — {complaint.title}\n"
        f"Category: {complaint.category}\n"
        f"Location: {where}\n"
        f"Resident: {who}\n"
        f"Reason: {reason}\n\n"
        f"{complaint.description}"
    )


async def _search_complaints(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        complaints = await repo.list_complaints(
            s,
            status=args.get("status"),
            resident_id=UUID(args["resident_id"]) if args.get("resident_id") else None,
            limit=int(args.get("limit", 10)),
        )
        return [c.model_dump(mode="json") for c in complaints]


async def _list_workers_by_category(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        workers = await repo.list_workers_by_category(
            s,
            category=args.get("category"),
            limit=int(args.get("limit", 20)),
        )
        return [w.model_dump(mode="json") for w in workers]


async def _record_resident_rating(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        cid = UUID(args["complaint_id"])
        await repo.record_rating(
            s,
            complaint_id=cid,
            resident_id=UUID(args["resident_id"]),
            stars=int(args["stars"]),
            comment=args.get("comment"),
        )
        if int(args["stars"]) <= 2:
            await repo.update_complaint_status(s, complaint_id=cid, new_status="open")
            return {"ok": True, "reopened": True}
        await repo.update_complaint_status(s, complaint_id=cid, new_status="closed")
        return {"ok": True, "closed": True}


async def _worker_status_update(args: dict[str, Any]) -> Any:
    action: str = args["action"]
    async with session_scope() as s:
        worker = await repo.find_worker_by_jid(s, wa_jid=args["worker_wa_jid"])
        if worker is None:
            return {"error": "worker not registered"}
        assignment = await repo.find_open_assignment_for_worker(s, worker_id=worker.id)
        if assignment is None:
            return {"error": "no open assignment for this worker"}

        complaint = await repo.get_complaint(s, complaint_id=assignment.complaint_id)
        resident = (
            await repo.get_resident_by_id(s, complaint.resident_id) if complaint else None
        )

        if action == "accept":
            await repo.update_assignment_status(
                s, assignment_id=assignment.id, new_status="accepted"
            )
            await repo.update_complaint_status(
                s, complaint_id=assignment.complaint_id, new_status="in_progress"
            )
            if complaint and resident:
                await _safe_notify(
                    resident.wa_jid,
                    f"Update on Ticket #{complaint.ticket_no}: {worker.name} has accepted "
                    f"and is on the way. We'll let you know when it's done.",
                )
            return {"ok": True, "complaint_id": str(assignment.complaint_id), "action": "accept"}

        if action == "done":
            await repo.update_assignment_status(
                s, assignment_id=assignment.id, new_status="done"
            )
            await repo.update_complaint_status(
                s, complaint_id=assignment.complaint_id, new_status="resolved"
            )
            if complaint and resident:
                await _safe_notify(
                    resident.wa_jid,
                    f"Ticket #{complaint.ticket_no} marked DONE by {worker.name}.\n"
                    f"Please reply with a number 1-5 to rate the service, or 'reopen' "
                    f"if the issue is not actually fixed.",
                )
            return {"ok": True, "complaint_id": str(assignment.complaint_id), "action": "done"}

        if action == "help":
            if complaint:
                body = (
                    f"🆘 Worker needs help on #{complaint.ticket_no}\n"
                    f"Worker: {worker.name} (+{worker.phone})\n"
                    f"Notes: {args.get('notes') or '(none)'}\n"
                    f"Complaint: {complaint.title}"
                )
                await broadcast_admin_alert(body)
            return {"ok": True, "complaint_id": str(assignment.complaint_id), "action": "help"}

        if action == "cancel":
            await repo.update_assignment_status(
                s, assignment_id=assignment.id, new_status="cancelled"
            )
            await repo.update_complaint_status(
                s, complaint_id=assignment.complaint_id, new_status="open"
            )
            if complaint and resident:
                await _safe_notify(
                    resident.wa_jid,
                    f"Update on Ticket #{complaint.ticket_no}: previous assignment was "
                    f"cancelled. We'll reassign shortly.",
                )
            return {"ok": True, "complaint_id": str(assignment.complaint_id), "action": "cancel"}

        return {"error": f"unknown action: {action}"}


async def _safe_notify(wa_jid: str, body: str) -> None:
    from .dispatch import send_text

    try:
        await send_text(to_jid=wa_jid, body=body)
    except Exception as e:  # noqa: BLE001
        log.warning("resident_notify_failed", jid=wa_jid, error=str(e))


async def _propose_workers(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        complaint = await repo.get_complaint(s, complaint_id=UUID(args["complaint_id"]))
        if complaint is None:
            return {"error": "complaint not found"}
        workers = await repo.propose_workers_for_complaint(
            s, category=complaint.category, limit=8
        )
        return {
            "complaint_id": str(complaint.id),
            "suggestions": [w.model_dump(mode="json") for w in workers],
        }


async def _update_complaint_status(args: dict[str, Any]) -> Any:
    async with session_scope() as s:
        c = await repo.update_complaint_status(
            s,
            complaint_id=UUID(args["complaint_id"]),
            new_status=args["new_status"],
        )
    if c is None:
        return {"error": "complaint not found"}
    # Notify resident on every status change made via the agent path.
    async with session_scope() as s:
        resident = await repo.get_resident_by_id(s, c.resident_id)
    if resident:
        body = (
            f"Update on Ticket #{c.ticket_no} — {c.title}\n"
            f"Status: {c.status.replace('_', ' ')}."
        )
        await _safe_notify(resident.wa_jid, body)
    return c.model_dump(mode="json")


_HANDLERS = {
    "register_or_get_resident": _register_or_get_resident,
    "update_resident_profile": _update_resident_profile,
    "classify_complaint": _classify_complaint,
    "create_complaint": _create_complaint,
    "escalate_to_admin": _escalate_to_admin,
    "search_complaints": _search_complaints,
    "list_workers_by_category": _list_workers_by_category,
    "propose_workers": _propose_workers,
    "update_complaint_status": _update_complaint_status,
    "record_resident_rating": _record_resident_rating,
    "worker_status_update": _worker_status_update,
}


async def serve_stdio() -> None:
    """Run the MCP server over stdio (used by OpenCLAW)."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
