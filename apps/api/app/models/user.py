"""System users table.

Source: docs/DATABASE_SCHEMA.md -- "users" section. Authority: ADR-009
(Authentication Architecture -- local users initially, LDAP/AD later).

``role`` has no defined value set in any architecture document yet -- left
as free text rather than inventing a taxonomy; RM-12 (API Service, which owns
authentication) is expected to define and enforce one. ``password_hash``
must never store a plaintext or reversibly-encrypted password (unlike
``camera_stream_profiles.rtsp_url_encrypted``, this is a one-way hash).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk


class User(Base):
    """A system user (operator, admin, etc.)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
