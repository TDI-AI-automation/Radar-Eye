"""Threat Review Center REST router -- RM-12 Phase 3 (reads) + Phase 4 (write).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Threat Review Center section.
  - GET /reviews
  - GET /reviews/{review_id}
  - PATCH /reviews/{review_id}
  - POST /reviews/{review_id}/confirm-military
  - POST /reviews/{review_id}/confirm-civilian
  - POST /reviews/{review_id}/escalate
  - POST /reviews/{review_id}/dismiss

CLAUDE.md's Human Review Rules: unknown uniforms must never be auto-
resolved; Confirm Military / Confirm Civilian / Escalate / Dismiss are the
only allowed operator actions. The four ``POST`` routes are the primary,
semantically-named entry points; ``PATCH`` is the generic form (a frontend
edit-form target) -- both funnel through the same ``_resolve()`` so there
is exactly one resolution rule, not five.

There is no dedicated human-review service (unlike incidents) -- system
code only ever *creates* review items (`docs/DATABASE_SCHEMA.md`'s
human_review_items); nothing in the pipeline auto-resolves one, so there is
no system-driven transition path to keep in sync with an operator-driven
one. Resolution logic living directly in this router (rather than a new
services/ package with a single caller) matches CLAUDE.md's "no unnecessary
abstraction" instruction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.models.user import ROLE_OPERATOR
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import (
    get_audit_logger,
    get_current_user,
    get_db_session,
    require_role,
)
from shared.schemas.api import ApiResponse
from shared.schemas.review import (
    RESOLUTION_STATUSES,
    HumanReviewSchema,
    ReviewResolutionRequestSchema,
)

router = APIRouter(tags=["Threat Review Center"], dependencies=[Depends(get_current_user)])


def _to_review_schema(item: HumanReviewItem) -> HumanReviewSchema:
    return HumanReviewSchema(
        review_item_id=item.id,
        camera_id=item.camera_id,
        track_id=item.track_id,
        reason=item.reason,
        status=item.status,  # type: ignore[arg-type]
    )


async def _resolve(
    session: AsyncSession,
    audit_logger: AuditLogger,
    user: DecodedToken,
    item: HumanReviewItem,
    new_status: str,
) -> HumanReviewSchema:
    if item.status != "OPEN":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Review item already resolved as {item.status}"
        )

    now = datetime.now(timezone.utc)
    item.status = new_status
    item.resolution = new_status
    item.resolved_by = str(user.user_id)
    item.resolved_at = now
    await session.flush()

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action=new_status,
        resource_type="human_review_item",
        resource_id=str(item.id),
        details={},
    )
    # Built before commit() -- commit() expires ORM attributes by default,
    # and a post-commit attribute access would lazy-load outside the
    # request's async context (MissingGreenlet).
    response_data = _to_review_schema(item)
    await session.commit()
    return response_data


async def _get_or_404(session: AsyncSession, review_id: uuid.UUID) -> HumanReviewItem:
    item = await HumanReviewRepository(session).get(review_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review item not found")
    return item


@router.get("/reviews", response_model=ApiResponse[list[HumanReviewSchema]])
async def list_reviews(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[HumanReviewSchema]]:
    items = await HumanReviewRepository(session).list()
    return ApiResponse(success=True, data=[_to_review_schema(i) for i in items])


@router.get("/reviews/{review_id}", response_model=ApiResponse[HumanReviewSchema])
async def get_review(
    review_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[HumanReviewSchema]:
    item = await _get_or_404(session, review_id)
    return ApiResponse(success=True, data=_to_review_schema(item))


@router.patch("/reviews/{review_id}", response_model=ApiResponse[HumanReviewSchema])
async def update_review(
    review_id: uuid.UUID,
    body: ReviewResolutionRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[HumanReviewSchema]:
    if body.status not in RESOLUTION_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"status must be one of {RESOLUTION_STATUSES}",
        )
    item = await _get_or_404(session, review_id)
    data = await _resolve(session, audit_logger, user, item, body.status)
    return ApiResponse(success=True, data=data)


@router.post("/reviews/{review_id}/confirm-military", response_model=ApiResponse[HumanReviewSchema])
async def confirm_military(
    review_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[HumanReviewSchema]:
    item = await _get_or_404(session, review_id)
    data = await _resolve(session, audit_logger, user, item, "CONFIRMED_MILITARY")
    return ApiResponse(success=True, data=data)


@router.post("/reviews/{review_id}/confirm-civilian", response_model=ApiResponse[HumanReviewSchema])
async def confirm_civilian(
    review_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[HumanReviewSchema]:
    item = await _get_or_404(session, review_id)
    data = await _resolve(session, audit_logger, user, item, "CONFIRMED_CIVILIAN")
    return ApiResponse(success=True, data=data)


@router.post("/reviews/{review_id}/escalate", response_model=ApiResponse[HumanReviewSchema])
async def escalate_review(
    review_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[HumanReviewSchema]:
    item = await _get_or_404(session, review_id)
    data = await _resolve(session, audit_logger, user, item, "ESCALATED")
    return ApiResponse(success=True, data=data)


@router.post("/reviews/{review_id}/dismiss", response_model=ApiResponse[HumanReviewSchema])
async def dismiss_review(
    review_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[HumanReviewSchema]:
    item = await _get_or_404(session, review_id)
    data = await _resolve(session, audit_logger, user, item, "DISMISSED")
    return ApiResponse(success=True, data=data)
