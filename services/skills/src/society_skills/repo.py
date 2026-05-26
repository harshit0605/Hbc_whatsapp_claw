"""Database access layer. All SQL lives here; MCP tools and HTTP routes call into it."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AssignmentOut,
    ComplaintMediaOut,
    ComplaintOut,
    ResidentOut,
    WorkerOut,
)


# ─────────────────────────── Residents ────────────────────────────────────


# A resident may be linked to multiple flats. We always present the most
# recently linked one to avoid non-determinism between calls.
_RESIDENT_BASE_SQL = """
select r.id, r.wa_jid, r.phone, r.display_name, r.language, r.status,
       r.created_at, r.updated_at,
       t.name as tower_name, f.flat_number as flat_number
from resident r
left join lateral (
    select rf.flat_id, rf.role
    from resident_flat rf
    where rf.resident_id = r.id
    order by case rf.role when 'owner' then 0 else 1 end, rf.flat_id desc
    limit 1
) rf on true
left join flat  f on f.id = rf.flat_id
left join tower t on t.id = f.tower_id
"""


async def get_resident_by_id(session: AsyncSession, resident_id: UUID) -> ResidentOut | None:
    row = (
        await session.execute(
            text(_RESIDENT_BASE_SQL + "where r.id = :id"),
            {"id": str(resident_id)},
        )
    ).mappings().first()
    return ResidentOut(**dict(row)) if row else None


async def find_resident_by_jid(session: AsyncSession, wa_jid: str) -> ResidentOut | None:
    row = (
        await session.execute(
            text(_RESIDENT_BASE_SQL + "where r.wa_jid = :jid"),
            {"jid": wa_jid},
        )
    ).mappings().first()
    return ResidentOut(**dict(row)) if row else None


def _phone_from_jid(jid: str) -> str | None:
    if "@" in jid:
        local = jid.split("@", 1)[0]
        return local if local.isdigit() else None
    return jid if jid.isdigit() else None


async def upsert_resident_stub(
    session: AsyncSession,
    *,
    wa_jid: str,
    display_name: str | None = None,
    language: str | None = None,
) -> tuple[ResidentOut, bool]:
    existing = await find_resident_by_jid(session, wa_jid)
    if existing:
        return existing, False

    phone = _phone_from_jid(wa_jid)
    await session.execute(
        text(
            """
            insert into resident (wa_jid, phone, display_name, language, status)
            values (:jid, :phone, :name, coalesce(:lang, 'en'), 'pending')
            on conflict (wa_jid) do nothing
            """
        ),
        {"jid": wa_jid, "phone": phone, "name": display_name, "lang": language},
    )
    created = await find_resident_by_jid(session, wa_jid)
    assert created is not None
    return created, True


async def update_resident_profile(
    session: AsyncSession,
    *,
    resident_id: UUID,
    display_name: str | None = None,
    language: str | None = None,
    tower_name: str | None = None,
    flat_number: str | None = None,
    status: str | None = None,
) -> ResidentOut:
    sets: list[str] = []
    params: dict[str, Any] = {"id": str(resident_id)}
    if display_name is not None:
        sets.append("display_name = :name")
        params["name"] = display_name
    if language is not None:
        sets.append("language = :lang")
        params["lang"] = language
    if status is not None:
        sets.append("status = :status")
        params["status"] = status
    sets.append("updated_at = now()")
    await session.execute(
        text(f"update resident set {', '.join(sets)} where id = :id"),
        params,
    )

    if tower_name and flat_number:
        tower_id = await ensure_tower(session, name=tower_name)
        flat_id = await ensure_flat(session, tower_id=tower_id, flat_number=flat_number)
        # Re-link: drop any prior flat assignments for this resident so a
        # correction ("oh I meant 1805") doesn't leave dangling links.
        await session.execute(
            text("delete from resident_flat where resident_id = :rid and flat_id <> :fid"),
            {"rid": str(resident_id), "fid": flat_id},
        )
        await session.execute(
            text(
                """
                insert into resident_flat (resident_id, flat_id, role)
                values (:rid, :fid, 'tenant')
                on conflict (resident_id, flat_id) do nothing
                """
            ),
            {"rid": str(resident_id), "fid": flat_id},
        )

    out = await get_resident_by_id(session, resident_id)
    assert out is not None
    return out


async def list_residents(
    session: AsyncSession, *, q: str | None = None, limit: int = 100
) -> list[ResidentOut]:
    where = ""
    params: dict[str, Any] = {"limit": limit}
    if q:
        where = "where (r.display_name ilike :q or r.phone ilike :q or t.name ilike :q)"
        params["q"] = f"%{q}%"
    rows = (
        await session.execute(
            text(_RESIDENT_BASE_SQL + f"{where} order by r.created_at desc limit :limit"),
            params,
        )
    ).mappings().all()
    return [ResidentOut(**dict(r)) for r in rows]


# ─────────────────────────── Towers / Flats ───────────────────────────────


async def ensure_tower(session: AsyncSession, *, name: str, floors: int = 20) -> int:
    normalized = name.strip().title()
    row = (
        await session.execute(
            text("select id from tower where lower(name) = lower(:n)"),
            {"n": normalized},
        )
    ).first()
    if row:
        return int(row[0])
    inserted = (
        await session.execute(
            text("insert into tower (name, floors) values (:n, :f) returning id"),
            {"n": normalized, "f": floors},
        )
    ).first()
    return int(inserted[0])


async def ensure_flat(session: AsyncSession, *, tower_id: int, flat_number: str) -> int:
    fnum = flat_number.strip().upper()
    row = (
        await session.execute(
            text(
                "select id from flat where tower_id = :t and flat_number = :f"
            ),
            {"t": tower_id, "f": fnum},
        )
    ).first()
    if row:
        return int(row[0])
    inserted = (
        await session.execute(
            text(
                "insert into flat (tower_id, flat_number) values (:t, :f) returning id"
            ),
            {"t": tower_id, "f": fnum},
        )
    ).first()
    return int(inserted[0])


# ─────────────────────────── Workers ──────────────────────────────────────


async def list_workers_by_category(
    session: AsyncSession, *, category: str | None = None, limit: int = 50
) -> list[WorkerOut]:
    params: dict[str, Any] = {"limit": limit}
    where = "where is_active = true"
    if category:
        where += " and :cat = any(categories)"
        params["cat"] = category
    rows = (
        await session.execute(
            text(
                f"""
                select id, wa_jid, phone, name, categories, is_active, notes
                from worker
                {where}
                order by name
                limit :limit
                """
            ),
            params,
        )
    ).mappings().all()
    return [WorkerOut(**dict(r)) for r in rows]


async def create_worker(
    session: AsyncSession,
    *,
    phone: str,
    name: str,
    categories: list[str],
    wa_jid: str | None = None,
    notes: str | None = None,
    is_active: bool = True,
) -> WorkerOut:
    row = (
        await session.execute(
            text(
                """
                insert into worker (phone, name, categories, wa_jid, notes, is_active)
                values (:phone, :name, :cats, :jid, :notes, :active)
                returning id, wa_jid, phone, name, categories, is_active, notes
                """
            ),
            {
                "phone": phone,
                "name": name,
                "cats": categories,
                "jid": wa_jid,
                "notes": notes,
                "active": is_active,
            },
        )
    ).mappings().first()
    assert row is not None
    return WorkerOut(**dict(row))


async def update_worker(
    session: AsyncSession,
    *,
    worker_id: UUID,
    name: str | None = None,
    categories: list[str] | None = None,
    is_active: bool | None = None,
    notes: str | None = None,
    wa_jid: str | None = None,
) -> WorkerOut:
    sets: list[str] = []
    params: dict[str, Any] = {"id": str(worker_id)}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if categories is not None:
        sets.append("categories = :cats")
        params["cats"] = categories
    if is_active is not None:
        sets.append("is_active = :active")
        params["active"] = is_active
    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes
    if wa_jid is not None:
        sets.append("wa_jid = :jid")
        params["jid"] = wa_jid
    sets.append("updated_at = now()")
    await session.execute(text(f"update worker set {', '.join(sets)} where id = :id"), params)
    row = (
        await session.execute(
            text(
                "select id, wa_jid, phone, name, categories, is_active, notes "
                "from worker where id = :id"
            ),
            {"id": str(worker_id)},
        )
    ).mappings().first()
    assert row is not None
    return WorkerOut(**dict(row))


async def get_worker_by_id(session: AsyncSession, worker_id: UUID) -> WorkerOut | None:
    row = (
        await session.execute(
            text(
                "select id, wa_jid, phone, name, categories, is_active, notes "
                "from worker where id = :id"
            ),
            {"id": str(worker_id)},
        )
    ).mappings().first()
    return WorkerOut(**dict(row)) if row else None


async def propose_workers_for_complaint(
    session: AsyncSession, *, category: str, limit: int = 5
) -> list[WorkerOut]:
    """Suggest workers ranked by category match, current load, and registration recency.

    Lower open_count (taking less work right now) ranks higher; workers whose
    `categories` contains the complaint category beat unrelated workers.
    """
    rows = (
        await session.execute(
            text(
                """
                select w.id, w.wa_jid, w.phone, w.name, w.categories, w.is_active, w.notes,
                       (
                           select count(*) from assignment a
                           where a.worker_id = w.id and a.status in ('pending','accepted')
                       ) as open_count,
                       case when :cat = any(w.categories) then 0 else 1 end as cat_rank
                from worker w
                where w.is_active = true
                order by cat_rank asc, open_count asc, w.name asc
                limit :limit
                """
            ),
            {"cat": category, "limit": limit},
        )
    ).mappings().all()
    return [WorkerOut(**{k: v for k, v in r.items() if k not in ("open_count", "cat_rank")}) for r in rows]


async def find_worker_by_jid(session: AsyncSession, wa_jid: str) -> WorkerOut | None:
    row = (
        await session.execute(
            text(
                "select id, wa_jid, phone, name, categories, is_active, notes "
                "from worker where wa_jid = :jid"
            ),
            {"jid": wa_jid},
        )
    ).mappings().first()
    return WorkerOut(**dict(row)) if row else None


# ─────────────────────────── Complaints ───────────────────────────────────


async def create_complaint(
    session: AsyncSession,
    *,
    resident_id: UUID,
    category: str,
    severity: str,
    title: str,
    description: str,
    raw_input: dict[str, Any] | None = None,
    flat_id: int | None = None,
    tower_id: int | None = None,
    media_keys: list[tuple[str, str, str | None]] | None = None,
) -> ComplaintOut:
    """media_keys: list of (kind, storage_key, mime)."""
    row = (
        await session.execute(
            text(
                """
                insert into complaint
                  (resident_id, flat_id, tower_id, category, severity, title, description, raw_input)
                values
                  (:rid, :fid, :tid, :cat, :sev, :title, :desc, coalesce(:raw, '{}'::jsonb))
                returning id, ticket_no
                """
            ),
            {
                "rid": str(resident_id),
                "fid": flat_id,
                "tid": tower_id,
                "cat": category,
                "sev": severity,
                "title": title,
                "desc": description,
                "raw": _jsonb(raw_input),
            },
        )
    ).mappings().first()
    assert row is not None
    complaint_id = row["id"]

    if media_keys:
        for kind, key, mime in media_keys:
            await session.execute(
                text(
                    """
                    insert into complaint_media (complaint_id, kind, storage_key, mime)
                    values (:cid, :kind, :key, :mime)
                    """
                ),
                {"cid": str(complaint_id), "kind": kind, "key": key, "mime": mime},
            )

    return (await get_complaint(session, complaint_id=complaint_id))  # type: ignore[return-value]


async def attach_media(
    session: AsyncSession,
    *,
    complaint_id: UUID,
    kind: str,
    storage_key: str,
    mime: str | None = None,
    size_bytes: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            insert into complaint_media (complaint_id, kind, storage_key, mime, bytes)
            values (:cid, :kind, :key, :mime, :bytes)
            """
        ),
        {
            "cid": str(complaint_id),
            "kind": kind,
            "key": storage_key,
            "mime": mime,
            "bytes": size_bytes,
        },
    )


async def get_complaint(session: AsyncSession, *, complaint_id: UUID) -> ComplaintOut | None:
    row = (
        await session.execute(
            text(
                """
                select c.id, c.ticket_no, c.resident_id, c.tower_id, c.flat_id,
                       c.category, c.severity, c.status, c.title, c.description,
                       c.created_at, c.updated_at, c.resolved_at,
                       t.name as tower_name, f.flat_number as flat_number,
                       r.display_name as resident_name, r.phone as resident_phone
                from complaint c
                left join tower    t on t.id = c.tower_id
                left join flat     f on f.id = c.flat_id
                left join resident r on r.id = c.resident_id
                where c.id = :id
                """
            ),
            {"id": str(complaint_id)},
        )
    ).mappings().first()
    if not row:
        return None
    media = await _list_media(session, complaint_id=complaint_id)
    return ComplaintOut(**dict(row), media=media)


async def list_complaints(
    session: AsyncSession,
    *,
    status: str | None = None,
    severity: str | None = None,
    resident_id: UUID | None = None,
    limit: int = 100,
) -> list[ComplaintOut]:
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if status:
        where.append("c.status = :status")
        params["status"] = status
    if severity:
        where.append("c.severity = :sev")
        params["sev"] = severity
    if resident_id:
        where.append("c.resident_id = :rid")
        params["rid"] = str(resident_id)
    wh = ("where " + " and ".join(where)) if where else ""
    rows = (
        await session.execute(
            text(
                f"""
                select c.id, c.ticket_no, c.resident_id, c.tower_id, c.flat_id,
                       c.category, c.severity, c.status, c.title, c.description,
                       c.created_at, c.updated_at, c.resolved_at,
                       t.name as tower_name, f.flat_number as flat_number,
                       r.display_name as resident_name, r.phone as resident_phone
                from complaint c
                left join tower    t on t.id = c.tower_id
                left join flat     f on f.id = c.flat_id
                left join resident r on r.id = c.resident_id
                {wh}
                order by
                  case c.severity
                    when 'critical' then 1
                    when 'high'     then 2
                    when 'medium'   then 3
                    when 'low'      then 4
                  end,
                  c.created_at desc
                limit :limit
                """
            ),
            params,
        )
    ).mappings().all()
    out: list[ComplaintOut] = []
    for r in rows:
        media = await _list_media(session, complaint_id=r["id"])
        out.append(ComplaintOut(**dict(r), media=media))
    return out


async def update_complaint_status(
    session: AsyncSession,
    *,
    complaint_id: UUID,
    new_status: str,
) -> ComplaintOut | None:
    resolved_clause = ", resolved_at = now()" if new_status in ("resolved", "closed") else ""
    await session.execute(
        text(
            f"update complaint set status = :s, updated_at = now() {resolved_clause} "
            f"where id = :id"
        ),
        {"s": new_status, "id": str(complaint_id)},
    )
    return await get_complaint(session, complaint_id=complaint_id)


async def _list_media(session: AsyncSession, *, complaint_id: UUID) -> list[ComplaintMediaOut]:
    rows = (
        await session.execute(
            text(
                "select id, kind, storage_key, mime, bytes "
                "from complaint_media where complaint_id = :cid "
                "order by created_at"
            ),
            {"cid": str(complaint_id)},
        )
    ).mappings().all()
    return [ComplaintMediaOut(**dict(r)) for r in rows]


# ─────────────────────────── Assignments ──────────────────────────────────


async def create_assignment(
    session: AsyncSession,
    *,
    complaint_id: UUID,
    worker_id: UUID,
    approved_by: UUID | None,
) -> AssignmentOut:
    row = (
        await session.execute(
            text(
                """
                insert into assignment (complaint_id, worker_id, approved_by, status)
                values (:cid, :wid, :aid, 'pending')
                returning id, complaint_id, worker_id, status, dispatched_at, closed_at, notes
                """
            ),
            {
                "cid": str(complaint_id),
                "wid": str(worker_id),
                "aid": str(approved_by) if approved_by else None,
            },
        )
    ).mappings().first()
    assert row is not None
    await session.execute(
        text("update complaint set status = 'assigned', updated_at = now() where id = :cid"),
        {"cid": str(complaint_id)},
    )
    w = (
        await session.execute(
            text("select name, phone from worker where id = :id"),
            {"id": str(worker_id)},
        )
    ).mappings().first()
    return AssignmentOut(**dict(row), worker_name=w["name"] if w else None, worker_phone=w["phone"] if w else None)


async def update_assignment_status(
    session: AsyncSession, *, assignment_id: UUID, new_status: str
) -> None:
    closed = ", closed_at = now()" if new_status in ("done", "cancelled") else ""
    await session.execute(
        text(f"update assignment set status = :s {closed} where id = :id"),
        {"s": new_status, "id": str(assignment_id)},
    )


async def find_open_assignment_for_worker(
    session: AsyncSession, *, worker_id: UUID
) -> AssignmentOut | None:
    row = (
        await session.execute(
            text(
                """
                select a.id, a.complaint_id, a.worker_id, a.status,
                       a.dispatched_at, a.closed_at, a.notes,
                       w.name as worker_name, w.phone as worker_phone
                from assignment a
                join worker w on w.id = a.worker_id
                where a.worker_id = :wid
                  and a.status in ('pending', 'accepted')
                order by a.dispatched_at desc
                limit 1
                """
            ),
            {"wid": str(worker_id)},
        )
    ).mappings().first()
    return AssignmentOut(**dict(row)) if row else None


async def list_assignments_for_complaint(
    session: AsyncSession, *, complaint_id: UUID
) -> list[AssignmentOut]:
    rows = (
        await session.execute(
            text(
                """
                select a.id, a.complaint_id, a.worker_id, a.status,
                       a.dispatched_at, a.closed_at, a.notes,
                       w.name as worker_name, w.phone as worker_phone
                from assignment a
                join worker w on w.id = a.worker_id
                where a.complaint_id = :cid
                order by a.dispatched_at desc
                """
            ),
            {"cid": str(complaint_id)},
        )
    ).mappings().all()
    return [AssignmentOut(**dict(r)) for r in rows]


# ─────────────────────────── Message log ──────────────────────────────────


async def log_message(
    session: AsyncSession,
    *,
    direction: str,
    wa_jid: str,
    body: str | None,
    media_keys: list[str] | None = None,
    resident_id: UUID | None = None,
    worker_id: UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            insert into message_log
              (direction, wa_jid, resident_id, worker_id, body, media_keys, meta)
            values
              (:dir, :jid, :rid, :wid, :body, :mks, coalesce(:meta, '{}'::jsonb))
            """
        ),
        {
            "dir": direction,
            "jid": wa_jid,
            "rid": str(resident_id) if resident_id else None,
            "wid": str(worker_id) if worker_id else None,
            "body": body,
            "mks": media_keys or [],
            "meta": _jsonb(meta),
        },
    )


# ─────────────────────────── Ratings ──────────────────────────────────────


async def record_rating(
    session: AsyncSession,
    *,
    complaint_id: UUID,
    resident_id: UUID,
    stars: int,
    comment: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            insert into rating (complaint_id, resident_id, stars, comment)
            values (:cid, :rid, :s, :c)
            """
        ),
        {"cid": str(complaint_id), "rid": str(resident_id), "s": stars, "c": comment},
    )


# ─────────────────────────── Admin users ──────────────────────────────────


async def find_admin_by_email(session: AsyncSession, email: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                "select id, email, password_hash, role, wa_jid, wa_phone "
                "from admin_user where email = :email"
            ),
            {"email": email.lower()},
        )
    ).mappings().first()
    return dict(row) if row else None


async def create_admin(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    role: str = "admin",
    wa_phone: str | None = None,
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                insert into admin_user (email, password_hash, role, wa_phone)
                values (:email, :ph, :role, :wp)
                returning id, email, role, wa_phone
                """
            ),
            {"email": email.lower(), "ph": password_hash, "role": role, "wp": wa_phone},
        )
    ).mappings().first()
    assert row is not None
    return dict(row)


async def count_admins(session: AsyncSession) -> int:
    row = (await session.execute(text("select count(*) from admin_user"))).first()
    return int(row[0]) if row else 0


async def count_complaints_by_status(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text("select status, count(*) from complaint group by status")
        )
    ).all()
    return {str(s): int(c) for s, c in rows}


async def count_complaints_by_category(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text("select category, count(*) from complaint group by category order by 2 desc")
        )
    ).all()
    return {str(c): int(n) for c, n in rows}


async def count_complaints_by_tower(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                select coalesce(t.name, 'unknown') as tower, count(*) as count
                from complaint c
                left join tower t on t.id = c.tower_id
                group by 1
                order by 2 desc
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def mean_time_to_resolve_seconds(session: AsyncSession) -> float | None:
    row = (
        await session.execute(
            text(
                """
                select extract(epoch from avg(resolved_at - created_at))
                from complaint
                where resolved_at is not null
                """
            )
        )
    ).first()
    return float(row[0]) if row and row[0] is not None else None


async def list_admins(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "select id, email, role, wa_phone, wa_jid, created_at "
                "from admin_user order by created_at"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def delete_admin(session: AsyncSession, admin_id: UUID) -> None:
    await session.execute(
        text("delete from admin_user where id = :id"), {"id": str(admin_id)}
    )


# ─────────────────────────── helpers ──────────────────────────────────────


def _jsonb(value: dict[str, Any] | None) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value)
