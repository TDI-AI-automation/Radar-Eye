"""Settings / user management REST router -- RM-12 Phase 4.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Settings section.
  - GET /users
  - PATCH /users/{user_id} (corrected from the contract's original
    path-less ``PATCH /users`` -- see that document's Settings notes)

Admin-only for both routes (per FRONTEND_BACKEND_CONTRACTS.md's Settings
purpose: "System administration"). ``PATCH`` updates ``role`` only --
``username``/``password_hash`` are not exposed through this route.

``GET``/``PATCH /config`` are explicitly out of scope for RM-12
(docs/OPEN_QUESTIONS.md Q-014) -- no persistence model for system
configuration is defined yet.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.user import KNOWN_ROLES, ROLE_ADMIN, User
from apps.api.app.repositories.user import UserRepository
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import get_audit_logger, get_db_session, require_role
from shared.schemas.api import ApiResponse
from shared.schemas.user import UserRoleUpdateRequestSchema, UserSchema

router = APIRouter(tags=["Settings"])


def _to_user_schema(user: User) -> UserSchema:
    return UserSchema(
        user_id=user.id, username=user.username, role=user.role, created_at=user.created_at
    )


@router.get("/users", response_model=ApiResponse[list[UserSchema]])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _actor: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[list[UserSchema]]:
    users = await UserRepository(session).list()
    return ApiResponse(success=True, data=[_to_user_schema(u) for u in users])


@router.patch("/users/{user_id}", response_model=ApiResponse[UserSchema])
async def update_user(
    user_id: uuid.UUID,
    body: UserRoleUpdateRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    actor: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[UserSchema]:
    if body.role not in KNOWN_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of {KNOWN_ROLES}"
        )

    target = await UserRepository(session).get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    old_role = target.role
    target.role = body.role
    await session.flush()
    await session.refresh(target)

    await audit_logger.record(
        session,
        actor_user_id=actor.user_id,
        action="UPDATE_USER_ROLE",
        resource_type="user",
        resource_id=str(target.id),
        details={"old_role": old_role, "new_role": target.role},
    )
    # Built before commit() -- commit() expires ORM attributes by default,
    # and a post-commit attribute access would lazy-load outside the
    # request's async context (MissingGreenlet).
    response_data = _to_user_schema(target)
    await session.commit()
    return ApiResponse(success=True, data=response_data)
