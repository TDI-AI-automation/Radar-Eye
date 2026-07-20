"""Evidence metadata tables: snapshots and event-clip recordings.

Source: docs/DATABASE_SCHEMA.md -- "snapshots", "recordings" sections.
Authority: ADR-017 (Recording Strategy). The database stores metadata only;
actual media files live on the filesystem (docs/DATABASE_SCHEMA.md --
"Recording Storage Layout").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk


class Snapshot(Base):
    """Snapshot metadata for a HIGH-threat incident."""

    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Recording(Base):
    """Event clip metadata for a HIGH-threat incident."""

    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
