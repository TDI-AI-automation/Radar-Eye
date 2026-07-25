"""Analytics REST router -- RM-12 Phase 3.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Analytics section.
  - GET /analytics/threats
  - GET /analytics/incidents
  - GET /analytics/cameras
  - GET /analytics/system

Per docs/RM-12_ARCHITECTURE.md §4, every route here is a straightforward
repository-query aggregation over an existing table -- no new analytics
infrastructure.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.repositories.audit_log import AuditLogRepository
from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.repositories.incident import IncidentRepository
from apps.api.app.security.dependencies import get_current_user, get_db_session
from shared.schemas.analytics import (
    CameraAnalyticsSchema,
    IncidentAnalyticsSchema,
    SystemAnalyticsSchema,
    ThreatAnalyticsSchema,
)
from shared.schemas.api import ApiResponse

router = APIRouter(tags=["Analytics"], dependencies=[Depends(get_current_user)])


@router.get("/analytics/threats", response_model=ApiResponse[ThreatAnalyticsSchema])
async def get_threat_analytics(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[ThreatAnalyticsSchema]:
    counts = await IncidentRepository(session).count_by_threat_level()
    return ApiResponse(success=True, data=ThreatAnalyticsSchema(counts_by_threat_level=counts))


@router.get("/analytics/incidents", response_model=ApiResponse[IncidentAnalyticsSchema])
async def get_incident_analytics(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[IncidentAnalyticsSchema]:
    repo = IncidentRepository(session)
    counts = await repo.count_by_status()
    total = await repo.count()
    return ApiResponse(
        success=True, data=IncidentAnalyticsSchema(total=total, counts_by_status=counts)
    )


@router.get("/analytics/cameras", response_model=ApiResponse[CameraAnalyticsSchema])
async def get_camera_analytics(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraAnalyticsSchema]:
    counts = await IncidentRepository(session).count_by_camera()
    total_cameras = await CameraRepository(session).count()
    return ApiResponse(
        success=True,
        data=CameraAnalyticsSchema(total_cameras=total_cameras, incident_counts_by_camera=counts),
    )


@router.get("/analytics/system", response_model=ApiResponse[SystemAnalyticsSchema])
async def get_system_analytics(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[SystemAnalyticsSchema]:
    total_cameras = await CameraRepository(session).count()
    total_incidents = await IncidentRepository(session).count()
    total_reviews = await HumanReviewRepository(session).count()
    total_audit_entries = await AuditLogRepository(session).count()
    return ApiResponse(
        success=True,
        data=SystemAnalyticsSchema(
            total_cameras=total_cameras,
            total_incidents=total_incidents,
            total_reviews=total_reviews,
            total_audit_entries=total_audit_entries,
        ),
    )
