"""Incident and incident-history tables.

Source: docs/DATABASE_SCHEMA.md -- "incidents", "incident_events" sections,
and "Incident Deduplication Constraint". Authority: ADR-025.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, updated_at_column, uuid_pk
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel

# Statuses that count as "still active" for the (camera_id, track_id) dedup
# constraint (docs/DATABASE_SCHEMA.md -- "Incident Deduplication Constraint";
# docs/INCIDENT_LIFECYCLE.md). RESOLVED and ARCHIVED are terminal states, not
# an active incident that a new detection could collide with.
_ACTIVE_INCIDENT_STATUSES = (
    IncidentStatus.NEW.value,
    IncidentStatus.ACTIVE.value,
    IncidentStatus.ACKNOWLEDGED.value,
)


class Incident(Base):
    """Primary incident record."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "ux_incidents_active_camera_track",
            "camera_id",
            "track_id",
            unique=True,
            postgresql_where=text(
                "status IN (" + ", ".join(repr(v) for v in _ACTIVE_INCIDENT_STATUSES) + ")"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    incident_type: Mapped[IncidentType] = mapped_column(
        SAEnum(
            IncidentType,
            name="incident_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    threat_level: Mapped[ThreatLevel] = mapped_column(
        SAEnum(
            ThreatLevel,
            name="threat_level",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(
            IncidentStatus,
            name="incident_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    threat_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentEvent(Base):
    """Incident lifecycle and audit history."""

    __tablename__ = "incident_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
