"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")

    op.execute(
        """
        create table tower (
            id          serial primary key,
            name        text not null unique,
            floors      int  not null,
            created_at  timestamptz not null default now()
        )
        """
    )

    op.execute(
        """
        create table flat (
            id          serial primary key,
            tower_id    int  not null references tower(id) on delete cascade,
            flat_number text not null,
            unique (tower_id, flat_number)
        )
        """
    )

    op.execute(
        """
        create table resident (
            id           uuid primary key default gen_random_uuid(),
            wa_jid       text unique not null,
            phone        text unique,
            display_name text,
            language     text not null default 'en',
            status       text not null default 'pending',  -- pending|verified|blocked
            created_at   timestamptz not null default now(),
            updated_at   timestamptz not null default now()
        )
        """
    )

    op.execute(
        """
        create table resident_flat (
            resident_id uuid not null references resident(id) on delete cascade,
            flat_id     int  not null references flat(id)     on delete cascade,
            role        text not null default 'tenant',  -- owner|tenant|family
            primary key (resident_id, flat_id)
        )
        """
    )

    op.execute(
        """
        create table worker (
            id          uuid primary key default gen_random_uuid(),
            wa_jid      text unique,
            phone       text unique not null,
            name        text not null,
            categories  text[] not null default '{}',
            is_active   bool not null default true,
            notes       text,
            created_at  timestamptz not null default now(),
            updated_at  timestamptz not null default now()
        )
        """
    )

    op.execute(
        "create type complaint_status as enum "
        "('open','triaging','assigned','in_progress','resolved','closed','rejected')"
    )
    op.execute(
        "create type complaint_severity as enum ('low','medium','high','critical')"
    )

    op.execute(
        """
        create table complaint (
            id           uuid primary key default gen_random_uuid(),
            ticket_no    serial unique,
            resident_id  uuid not null references resident(id),
            flat_id      int  references flat(id),
            tower_id     int  references tower(id),
            category     text not null,
            severity     complaint_severity not null default 'low',
            status       complaint_status   not null default 'open',
            title        text not null,
            description  text not null,
            raw_input    jsonb not null default '{}'::jsonb,
            created_at   timestamptz not null default now(),
            updated_at   timestamptz not null default now(),
            resolved_at  timestamptz
        )
        """
    )
    op.execute("create index complaint_status_idx   on complaint(status)")
    op.execute("create index complaint_severity_idx on complaint(severity)")
    op.execute("create index complaint_resident_idx on complaint(resident_id)")
    op.execute("create index complaint_tower_idx    on complaint(tower_id)")

    op.execute(
        """
        create table complaint_media (
            id            uuid primary key default gen_random_uuid(),
            complaint_id  uuid not null references complaint(id) on delete cascade,
            kind          text not null,  -- image|audio|video|document
            storage_key   text not null,
            mime          text,
            bytes         int,
            created_at    timestamptz not null default now()
        )
        """
    )

    op.execute(
        """
        create table admin_user (
            id            uuid primary key default gen_random_uuid(),
            email         text unique not null,
            password_hash text,
            wa_phone      text,
            wa_jid        text,
            role          text not null default 'admin',  -- admin|super_admin
            created_at    timestamptz not null default now()
        )
        """
    )

    op.execute(
        """
        create table assignment (
            id            uuid primary key default gen_random_uuid(),
            complaint_id  uuid not null references complaint(id) on delete cascade,
            worker_id     uuid not null references worker(id),
            approved_by   uuid references admin_user(id),
            status        text not null default 'pending',  -- pending|accepted|done|cancelled
            dispatched_at timestamptz not null default now(),
            closed_at     timestamptz,
            notes         text
        )
        """
    )
    op.execute("create index assignment_complaint_idx on assignment(complaint_id)")
    op.execute("create index assignment_worker_idx    on assignment(worker_id)")

    op.execute(
        """
        create table message_log (
            id           bigserial primary key,
            direction    text not null,  -- in|out
            wa_jid       text not null,
            resident_id  uuid references resident(id),
            worker_id    uuid references worker(id),
            body         text,
            media_keys   text[] not null default '{}',
            meta         jsonb  not null default '{}'::jsonb,
            created_at   timestamptz not null default now()
        )
        """
    )
    op.execute("create index message_log_jid_time_idx on message_log(wa_jid, created_at desc)")

    op.execute(
        """
        create table rating (
            id           uuid primary key default gen_random_uuid(),
            complaint_id uuid not null references complaint(id) on delete cascade,
            resident_id  uuid not null references resident(id),
            stars        int not null check (stars between 1 and 5),
            comment      text,
            created_at   timestamptz not null default now()
        )
        """
    )


def downgrade() -> None:
    for tbl in (
        "rating",
        "message_log",
        "assignment",
        "admin_user",
        "complaint_media",
        "complaint",
        "worker",
        "resident_flat",
        "resident",
        "flat",
        "tower",
    ):
        op.execute(f"drop table if exists {tbl} cascade")
    op.execute("drop type if exists complaint_status")
    op.execute("drop type if exists complaint_severity")
