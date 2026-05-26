"""FastAPI HTTP API consumed by the Next.js admin portal.

This is the ONLY surface that can trigger send_dispatch_to_worker — the
agent's MCP tool catalog deliberately omits dispatch, enforcing the
human-in-the-loop rule structurally rather than via prompt.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from passlib.hash import bcrypt

from . import repo, storage
from .db import session_scope
from .dispatch import broadcast_admin_alert, send_text
from .logging_setup import configure_logging, get_logger
from .models import (
    AssignmentOut,
    ComplaintOut,
    GenericOk,
    MessageLogIn,
    ResidentOut,
    WorkerIn,
    WorkerOut,
)
from .settings import get_settings

configure_logging()
log = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        storage.ensure_bucket()
    except Exception as e:  # noqa: BLE001
        log.warning("bucket_init_failed", error=str(e))

    s = get_settings()
    if not s.admin_alert_jid_list:
        log.warning(
            "admin_alert_jids_empty",
            detail="critical-issue WhatsApp alerts will be no-ops until ADMIN_ALERT_JIDS is set",
        )

    boot_email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    boot_pw = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if boot_email and boot_pw:
        try:
            async with session_scope() as sess:
                if await repo.count_admins(sess) == 0:
                    await repo.create_admin(
                        sess,
                        email=boot_email,
                        password_hash=bcrypt.hash(boot_pw),
                        role="super_admin",
                    )
                    log.info("bootstrap_admin_created", email=boot_email)
        except Exception as e:  # noqa: BLE001
            # DB may not be migrated yet on first boot; an external migrator
            # runs first, and the next request handler will surface real errors.
            log.warning("bootstrap_admin_skipped", error=str(e))
    yield


app = FastAPI(title="society-skills HTTP API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth: shared internal bearer token ─────────────────────────────────────


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().skills_api_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad token")


AuthDep = Depends(require_token)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ─── Admin auth (used by NextAuth credentials provider) ────────────────────


@app.post("/auth/login", dependencies=[AuthDep])
async def auth_login(payload: dict[str, str]) -> dict[str, Any]:
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email and password required")
    async with session_scope() as s:
        admin = await repo.find_admin_by_email(s, email)
    if not admin or not admin.get("password_hash"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not bcrypt.verify(password, admin["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return {
        "id": str(admin["id"]),
        "email": admin["email"],
        "role": admin["role"],
    }


# ─── Complaints / queue ──────────────────────────────────────────────────────


@app.get("/complaints", dependencies=[AuthDep])
async def list_complaints(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[ComplaintOut]:
    async with session_scope() as s:
        items = await repo.list_complaints(
            s, status=status, severity=severity, limit=limit
        )
    return [_with_presigned(c) for c in items]


@app.get("/complaints/{complaint_id}", dependencies=[AuthDep])
async def get_complaint(complaint_id: UUID) -> ComplaintOut:
    async with session_scope() as s:
        c = await repo.get_complaint(s, complaint_id=complaint_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return _with_presigned(c)


@app.get("/complaints/{complaint_id}/assignments", dependencies=[AuthDep])
async def get_complaint_assignments(complaint_id: UUID) -> list[AssignmentOut]:
    async with session_scope() as s:
        return await repo.list_assignments_for_complaint(s, complaint_id=complaint_id)


@app.get("/complaints/{complaint_id}/proposed-workers", dependencies=[AuthDep])
async def get_proposed_workers(complaint_id: UUID) -> list[WorkerOut]:
    async with session_scope() as s:
        c = await repo.get_complaint(s, complaint_id=complaint_id)
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return await repo.propose_workers_for_complaint(s, category=c.category, limit=8)


@app.post("/complaints/{complaint_id}/status", dependencies=[AuthDep])
async def post_complaint_status(complaint_id: UUID, payload: dict[str, str]) -> ComplaintOut:
    new = payload.get("status")
    if not new:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status required")
    async with session_scope() as s:
        c = await repo.update_complaint_status(s, complaint_id=complaint_id, new_status=new)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    notify_error: str | None = None
    try:
        await _notify_resident_status_change(c)
    except Exception as e:  # noqa: BLE001
        log.warning("status_notify_failed", complaint_id=str(complaint_id), error=str(e))
        notify_error = str(e)
    # Surface the failure to the caller via header so the UI can show a banner.
    if notify_error:
        from fastapi.responses import JSONResponse

        body = _with_presigned(c).model_dump(mode="json")
        return JSONResponse(content=body, headers={"X-Resident-Notify-Error": notify_error})
    return _with_presigned(c)


@app.post("/complaints/{complaint_id}/media", dependencies=[AuthDep])
async def attach_media_to_complaint(
    complaint_id: UUID,
    file: UploadFile = File(...),
    kind: str = Form("image"),
) -> GenericOk:
    data = await file.read()
    key = storage.put_bytes(data, kind=kind, mime=file.content_type)
    async with session_scope() as s:
        c = await repo.get_complaint(s, complaint_id=complaint_id)
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        await repo.attach_media(
            s,
            complaint_id=complaint_id,
            kind=kind,
            storage_key=key,
            mime=file.content_type,
            size_bytes=len(data),
        )
    return GenericOk(detail=key)


# ─── Dispatch (the human-approval gate) ──────────────────────────────────────


@app.post("/complaints/{complaint_id}/dispatch", dependencies=[AuthDep])
async def dispatch(complaint_id: UUID, payload: dict[str, Any]) -> AssignmentOut:
    worker_id = payload.get("worker_id")
    approved_by = payload.get("approved_by")
    if not worker_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "worker_id required")

    async with session_scope() as s:
        complaint = await repo.get_complaint(s, complaint_id=complaint_id)
        if complaint is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "complaint not found")
        worker = await repo.get_worker_by_id(s, UUID(worker_id))
        if worker is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "worker not found")
        if not worker.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "worker is inactive")
        if not worker.wa_jid:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "worker has no WhatsApp JID — they need to message the bot once first",
            )
        assignment = await repo.create_assignment(
            s,
            complaint_id=complaint_id,
            worker_id=worker.id,
            approved_by=UUID(approved_by) if approved_by else None,
        )

    body = _format_worker_dispatch(complaint, worker)
    # Pass presigned URLs (not raw object keys) so the gateway can fetch
    # without being on the same network as our object store.
    media_urls = [
        storage.presigned_get(m.storage_key) for m in complaint.media if m.kind == "image"
    ]
    try:
        await send_text(
            to_jid=worker.wa_jid,
            body=body,
            media_urls=media_urls or None,
        )
    except Exception as e:
        log.error("worker_dispatch_send_failed", error=str(e), assignment_id=str(assignment.id))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"assignment created but WhatsApp send failed: {e}",
        ) from e
    return assignment


def _format_worker_dispatch(c: ComplaintOut, w: WorkerOut) -> str:
    loc = []
    if c.tower_name:
        loc.append(f"Tower {c.tower_name}")
    if c.flat_number:
        loc.append(f"Flat {c.flat_number}")
    where = ", ".join(loc) or "location TBD"
    return (
        f"Hi {w.name}, new task #{c.ticket_no}\n"
        f"{c.category.upper()} — {c.title}\n"
        f"Where: {where}\n"
        f"Reported by: {c.resident_name or 'resident'} "
        f"(+{c.resident_phone or '—'})\n\n"
        f"{c.description}\n\n"
        f"Reply ACCEPT to take ticket #{c.ticket_no}, DONE when finished, "
        f"or HELP if blocked."
    )


# ─── Workers directory ──────────────────────────────────────────────────────


@app.get("/workers/lookup", dependencies=[AuthDep])
async def lookup_worker(wa_jid: str) -> WorkerOut:
    async with session_scope() as s:
        w = await repo.find_worker_by_jid(s, wa_jid=wa_jid)
    if w is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "worker not found")
    return w


@app.get("/workers", dependencies=[AuthDep])
async def list_workers(category: str | None = None) -> list[WorkerOut]:
    async with session_scope() as s:
        return await repo.list_workers_by_category(s, category=category, limit=500)


@app.post("/workers", dependencies=[AuthDep])
async def create_worker(payload: WorkerIn) -> WorkerOut:
    async with session_scope() as s:
        return await repo.create_worker(
            s,
            phone=payload.phone,
            name=payload.name,
            categories=payload.categories,
            wa_jid=payload.wa_jid,
            notes=payload.notes,
            is_active=payload.is_active,
        )


@app.patch("/workers/{worker_id}", dependencies=[AuthDep])
async def patch_worker(worker_id: UUID, payload: dict[str, Any]) -> WorkerOut:
    async with session_scope() as s:
        return await repo.update_worker(
            s,
            worker_id=worker_id,
            name=payload.get("name"),
            categories=payload.get("categories"),
            is_active=payload.get("is_active"),
            notes=payload.get("notes"),
            wa_jid=payload.get("wa_jid"),
        )


# ─── Residents directory ────────────────────────────────────────────────────


@app.get("/residents", dependencies=[AuthDep])
async def list_residents(q: str | None = None) -> list[ResidentOut]:
    async with session_scope() as s:
        return await repo.list_residents(s, q=q)


# ─── Media upload (called by the agent's media_handler plugin) ──────────────


@app.post("/media", dependencies=[AuthDep])
async def upload_media(file: UploadFile = File(...), kind: str = "image") -> dict[str, str]:
    data = await file.read()
    key = storage.put_bytes(data, kind=kind, mime=file.content_type)
    return {"storage_key": key, "mime": file.content_type or "", "size": str(len(data))}


# ─── Stats for dashboard ────────────────────────────────────────────────────


@app.get("/stats", dependencies=[AuthDep])
async def stats() -> dict[str, Any]:
    async with session_scope() as s:
        by_status = await repo.count_complaints_by_status(s)
        by_category = await repo.count_complaints_by_category(s)
        by_tower = await repo.count_complaints_by_tower(s)
        mttr_seconds = await repo.mean_time_to_resolve_seconds(s)
    return {
        "by_status": by_status,
        "by_category": by_category,
        "by_tower": by_tower,
        "mttr_seconds": mttr_seconds,
    }


# ─── Audit log inbound (called by the OpenCLAW audit_logger plugin) ─────────


@app.post("/message-log", dependencies=[AuthDep])
async def post_message_log(payload: MessageLogIn) -> GenericOk:
    async with session_scope() as s:
        resident = await repo.find_resident_by_jid(s, wa_jid=payload.wa_jid)
        worker = None if resident else await repo.find_worker_by_jid(s, wa_jid=payload.wa_jid)
        await repo.log_message(
            s,
            direction=payload.direction,
            wa_jid=payload.wa_jid,
            body=payload.body,
            media_keys=payload.media_keys,
            resident_id=resident.id if resident else None,
            worker_id=worker.id if worker else None,
            meta=payload.meta,
        )
    return GenericOk()


# ─── Admin user management ──────────────────────────────────────────────────


@app.get("/admins", dependencies=[AuthDep])
async def get_admins() -> list[dict[str, Any]]:
    async with session_scope() as s:
        return await repo.list_admins(s)


@app.post("/admins", dependencies=[AuthDep])
async def post_admin(payload: dict[str, str]) -> dict[str, Any]:
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    role = payload.get("role") or "admin"
    if not email or len(password) < 8:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "email and password (>= 8 chars) required"
        )
    async with session_scope() as s:
        return await repo.create_admin(
            s, email=email, password_hash=bcrypt.hash(password), role=role,
            wa_phone=payload.get("wa_phone"),
        )


@app.delete("/admins/{admin_id}", dependencies=[AuthDep])
async def del_admin(admin_id: UUID) -> GenericOk:
    async with session_scope() as s:
        await repo.delete_admin(s, admin_id)
    return GenericOk()


@app.post("/transcribe", dependencies=[AuthDep])
async def transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    """Voice-note transcription. v1 returns 501 by default; wire in your STT
    provider (Whisper, AssemblyAI, Sarvam, etc.) by setting STT_PROVIDER_URL
    in env and uncommenting the proxy below."""
    stt_url = os.getenv("STT_PROVIDER_URL")
    if not stt_url:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "transcription not configured — set STT_PROVIDER_URL or replace this stub",
        )
    import httpx

    data = await file.read()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            stt_url,
            files={"file": (file.filename or "voice", data, file.content_type or "audio/ogg")},
        )
        resp.raise_for_status()
        out = resp.json()
    return {"text": out.get("text") or out.get("transcription") or ""}


@app.post("/admin/test-alert", dependencies=[AuthDep])
async def test_alert(payload: dict[str, str]) -> GenericOk:
    body = payload.get("body") or "Test alert from society admin portal"
    await broadcast_admin_alert(body)
    return GenericOk(detail="dispatched")


# ─── Helpers ────────────────────────────────────────────────────────────────


def _with_presigned(c: ComplaintOut) -> ComplaintOut:
    for m in c.media:
        try:
            m.presigned_url = storage.presigned_get(m.storage_key)
        except Exception as e:  # noqa: BLE001
            log.warning("presign_failed", key=m.storage_key, error=str(e))
    return c


async def _notify_resident_status_change(c: ComplaintOut) -> None:
    async with session_scope() as s:
        resident = await repo.get_resident_by_id(s, c.resident_id)
    if resident is None:
        return
    pretty = {
        "open": "back to open",
        "triaging": "being triaged",
        "assigned": "assigned to a worker",
        "in_progress": "in progress",
        "resolved": "resolved ✅ — please rate 1-5",
        "closed": "closed",
        "rejected": "marked invalid",
    }.get(c.status, c.status)
    body = (
        f"Update on Ticket #{c.ticket_no} — {c.title}\n"
        f"Status: {pretty}.\n"
    )
    if c.status == "resolved":
        body += (
            f"Reply with a number 1-5 to rate, or 'reopen' if not actually fixed."
        )
    else:
        body += f"Reply 'status #{c.ticket_no}' anytime to check again."
    await send_text(to_jid=resident.wa_jid, body=body)
