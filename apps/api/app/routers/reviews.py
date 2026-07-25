"""Threat Review Center REST router -- RM-12 Phase 3 (read routes only).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Threat Review Center section.
  - GET /reviews
  - GET /reviews/{review_id}

The four write routes (``PATCH /reviews/{id}``,
``POST /reviews/{id}/confirm-military|confirm-civilian|escalate|dismiss``)
are Phase 4 (mutating, operator-gated, audit-logged) -- CLAUDE.md's Human
Review Rules: unknown uniforms must never be auto-resolved, so these four
actions are the only allowed resolutions and none of them belongs in a
read-only phase.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.security.dependencies import get_current_user, get_db_session
from shared.schemas.api import ApiResponse
from shared.schemas.review import HumanReviewSchema

router = APIRouter(tags=["Threat Review Center"], dependencies=[Depends(get_current_user)])


def _to_review_schema(item: HumanReviewItem) -> HumanReviewSchema:
    return HumanReviewSchema(
        review_item_id=item.id,
        camera_id=item.camera_id,
        track_id=item.track_id,
        reason=item.reason,
        status=item.status,  # type: ignore[arg-type]
    )


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
    item = await HumanReviewRepository(session).get(review_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review item not found")
    return ApiResponse(success=True, data=_to_review_schema(item))
