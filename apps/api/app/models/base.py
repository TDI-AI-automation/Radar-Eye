"""Declarative base and shared column helpers for all ORM models.

Source: docs/DATABASE_SCHEMA.md. Authority: ADR-008 (metadata-only storage --
raw frames/detections/tracking data are never persisted; only the tables
enumerated in DATABASE_SCHEMA.md exist here).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every Radar Eye ORM model."""


def uuid_pk() -> Mapped[uuid.UUID]:
    """A UUID primary key column, server-independent (generated in Python)."""
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
