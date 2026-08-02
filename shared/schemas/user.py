"""User API schemas -- RM-12 Phase 4.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Settings section
  (GET /users, PATCH /users/{user_id} -- corrected from the contract's
  original path-less ``PATCH /users``, see that document's Settings notes).
``password_hash`` is never exposed through any of these schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class UserSchema(BaseModel):
    """Returned by ``GET /users``."""

    user_id: uuid.UUID
    username: str
    role: str
    created_at: datetime


class UserRoleUpdateRequestSchema(BaseModel):
    """Body of ``PATCH /users/{user_id}`` -- role changes only.
    ``username``/``password_hash`` are not updatable through this route."""

    role: str
