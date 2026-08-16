"""System users table.

Source: docs/DATABASE_SCHEMA.md -- "users" section. Authority: ADR-009
(Authentication Architecture -- local users initially, LDAP/AD later).

``role`` has no ratified value set in any architecture document yet --
``KNOWN_ROLES``/``ROLE_RANK`` below are docs/RM-12_ARCHITECTURE.md §3.2's
*proposed* taxonomy (admin/operator/viewer), used by
``apps.api.app.security.dependencies.require_role`` -- not a ratified
answer to docs/OPEN_QUESTIONS.md's open item. The column stays free-text
``str`` at the DB level deliberately, not a CHECK constraint or enum, so
that question can still be resolved without a migration. ``password_hash``
must never store a plaintext or reversibly-encrypted password (unlike
``camera_stream_profiles.rtsp_url_encrypted``, this is a one-way hash).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

KNOWN_ROLES = (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN)

ROLE_RANK: dict[str, int] = {ROLE_VIEWER: 0, ROLE_OPERATOR: 1, ROLE_ADMIN: 2}
"""Ordering for "minimum role" checks -- higher rank can do everything a
lower rank can. A role not in this mapping ranks below every known role
(see ``security.dependencies.require_role``), never above."""


class User(Base):
    """A system user (operator, admin, etc.)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
