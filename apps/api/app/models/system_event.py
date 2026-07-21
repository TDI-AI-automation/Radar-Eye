"""Operational system events table.

Source: docs/DATABASE_SCHEMA.md -- "system_events" section.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk
from shared.events.payloads import SystemEventSeverity

_SEVERITY_VALUES = get_args(SystemEventSeverity)


class SystemEvent(Base):
    """Operational event surfaced to the frontend (docs/EVENT_CONTRACTS.md -- SystemEvent)."""

    __tablename__ = "system_events"
    __table_args__ = (
        CheckConstraint(
            f"severity IN ({', '.join(repr(v) for v in _SEVERITY_VALUES)})",
            name="ck_system_events_severity",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
