"""User action audit history table.

Source: docs/DATABASE_SCHEMA.md -- "audit_log" section. Authority: ADR-008
(metadata-only storage -- audit history is one of the four persisted
categories, alongside incidents, evidence metadata, and configuration).

Distinct from ``incident_events`` (incident-lifecycle history, FK-scoped to
a single incident) and ``system_events`` (operational/runtime events, not
tied to a user action) -- ``audit_log`` records *who did what*, independent
of whether the action relates to any incident at all (a camera update, a
config change, a user-management action, a calibration action).
``actor_user_id`` is nullable to allow system-generated actions with no
human actor, per docs/DATABASE_SCHEMA.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk


class AuditLog(Base):
    """A single audited user (or system-generated) action."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = created_at_column()
