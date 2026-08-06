"""Media Distribution Interface / per-subsystem health tables (ADR-028,
Media Architecture Reset).

Cross-process fact sharing follows the same established pattern as
Camera Observed State (``Camera.status``/``fps``/etc.): the publishing/
reporting process and the reading process(es) are separate OS
processes that don't share memory, so Postgres is the mechanism, not a
bespoke discovery/health protocol.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, updated_at_column, uuid_pk


class CameraMediaEndpoint(Base):
    """One row per (camera, publishing subsystem) -- how to reach that
    subsystem's currently-published media, per the Media Distribution
    Interface (``shared/media_transport``). ``transport``/``address``
    are opaque outside ``shared.media_transport.build_source_element()``
    -- no reader interprets ``address`` itself.

    Sole writer of a given row: the publishing subsystem named in
    ``subsystem`` (e.g. "ingestion" writes only ingestion's row for a
    camera; "ai", from Phase 5 onward, writes only its own). Readers
    (any consumer subscribing to that subsystem's media) never write.
    """

    __tablename__ = "camera_media_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "camera_id", "subsystem", name="uq_camera_media_endpoints_camera_subsystem"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    subsystem: Mapped[str] = mapped_column(String, nullable=False)
    transport: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = updated_at_column()


class CameraSubsystemHealth(Base):
    """One row per (camera, subsystem) -- that subsystem's own,
    independently-reported health fact for that camera. Replaces the
    single overloaded ``Camera.status`` column's role as "the" health
    signal (``Camera.status`` remains Camera Ingestion's own
    connectivity fact once it migrates in Phase 1b, but every other
    subsystem's health is reported here, never by writing ``Camera``).

    Sole writer of a given row: the subsystem named in ``subsystem``.
    Nothing reads another subsystem's row in order to decide its own
    behavior -- only the Health aggregation layer (``apps.api``) reads
    across all of them.
    """

    __tablename__ = "camera_subsystem_health"
    __table_args__ = (
        UniqueConstraint(
            "camera_id", "subsystem", name="uq_camera_subsystem_health_camera_subsystem"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    subsystem: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = updated_at_column()
