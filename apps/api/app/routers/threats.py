"""Live threat REST router -- RM-12 Phase 3.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Live Monitoring / Tactical Map
  sections. GET /threats/active.

See apps.api.app.threats.ActiveThreatCache for why this endpoint reads
from an in-memory cache rather than a repository, and why it is currently
unfed (honestly empty) until Phase 5 wires the event-bus subscription that
calls ``record()``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from apps.api.app.security.dependencies import get_current_user
from apps.api.app.threats import ActiveThreatCache
from shared.schemas.api import ApiResponse
from shared.schemas.threat import ActiveThreatSchema

router = APIRouter(tags=["Live Monitoring"], dependencies=[Depends(get_current_user)])


def _get_active_threat_cache(request: Request) -> ActiveThreatCache:
    cache: ActiveThreatCache | None = getattr(request.app.state, "active_threat_cache", None)
    if cache is None:
        cache = ActiveThreatCache()
        request.app.state.active_threat_cache = cache
    return cache


@router.get("/threats/active", response_model=ApiResponse[list[ActiveThreatSchema]])
async def list_active_threats(
    cache: ActiveThreatCache = Depends(_get_active_threat_cache),  # noqa: B008
) -> ApiResponse[list[ActiveThreatSchema]]:
    return ApiResponse(success=True, data=cache.get_active())
