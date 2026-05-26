"""Pydantic DTOs shared between MCP tools, HTTP API, and the admin portal."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high", "critical"]
Category = Literal[
    "plumbing",
    "electrical",
    "lift",
    "cleanliness",
    "garbage",
    "security",
    "water",
    "gas",
    "carpentry",
    "pest_control",
    "common_area",
    "other",
]
ComplaintStatus = Literal[
    "open", "triaging", "assigned", "in_progress", "resolved", "closed", "rejected"
]
ResidentStatus = Literal["pending", "verified", "blocked"]
MediaKind = Literal["image", "audio", "video", "document"]
AssignmentStatus = Literal["pending", "accepted", "done", "cancelled"]


class ResidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wa_jid: str
    phone: str | None
    display_name: str | None
    language: str
    status: ResidentStatus
    tower_name: str | None = None
    flat_number: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wa_jid: str | None
    phone: str
    name: str
    categories: list[str]
    is_active: bool
    notes: str | None = None


class WorkerIn(BaseModel):
    phone: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1)
    categories: list[str] = Field(default_factory=list)
    wa_jid: str | None = None
    notes: str | None = None
    is_active: bool = True


class ComplaintMediaOut(BaseModel):
    id: UUID
    kind: MediaKind
    storage_key: str
    mime: str | None = None
    bytes: int | None = None
    presigned_url: str | None = None


class ComplaintOut(BaseModel):
    id: UUID
    ticket_no: int
    resident_id: UUID
    tower_id: int | None
    flat_id: int | None
    tower_name: str | None
    flat_number: str | None
    resident_name: str | None
    resident_phone: str | None
    category: str
    severity: Severity
    status: ComplaintStatus
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    media: list[ComplaintMediaOut] = Field(default_factory=list)


class AssignmentOut(BaseModel):
    id: UUID
    complaint_id: UUID
    worker_id: UUID
    worker_name: str | None = None
    worker_phone: str | None = None
    status: AssignmentStatus
    dispatched_at: datetime
    closed_at: datetime | None = None
    notes: str | None = None


class ClassificationOut(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    rationale: str | None = None


class ProposeDispatchOut(BaseModel):
    complaint_id: UUID
    suggestions: list[WorkerOut]
    reason: str


class RegisterResidentOut(BaseModel):
    resident: ResidentOut
    is_new: bool


class CreateComplaintOut(BaseModel):
    complaint: ComplaintOut
    is_critical: bool


class GenericOk(BaseModel):
    ok: bool = True
    detail: str | None = None


class MessageLogIn(BaseModel):
    direction: Literal["in", "out"]
    wa_jid: str
    body: str | None = None
    media_keys: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
