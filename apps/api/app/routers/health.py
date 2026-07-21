"""Health monitoring REST router.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — System Health & Camera Management sections.
Endpoints:
  - GET /api/v1/health/system
  - GET /api/v1/health/gpu
  - GET /api/v1/health/storage
  - GET /api/v1/health/cameras
  - GET /api/v1/cameras/{camera_id}/health
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.health.collector import HealthCollector
from apps.api.app.repositories.camera import CameraRepository
from shared.schemas.api import ApiResponse
from shared.schemas.camera import CameraHealthSchema
from shared.schemas.health import (
    GPUHealthSchema,
    StorageHealthSchema,
    SystemHealthSchema,
)

router = APIRouter(tags=["Health & Monitoring"])


def _get_collector(request: Request) -> HealthCollector:
    """Retrieve HealthCollector from FastAPI app.state or create default."""
    collector: HealthCollector | None = getattr(request.app.state, "health_collector", None)
    if collector is None:
        collector = HealthCollector()
        request.app.state.health_collector = collector
    return collector


async def _get_db_session(request: Request) -> Any:
    """Dependency helper to yield DB session if factory present."""
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory:
        async with session_factory() as session:
            yield session
    else:
        yield None


@router.get(
    "/api/v1/health/system",
    response_model=ApiResponse[SystemHealthSchema],
    summary="Get aggregated system health metrics",
)
async def get_system_health(
    request: Request,
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
    db_session: AsyncSession | None = Depends(_get_db_session),  # noqa: B008
) -> ApiResponse[SystemHealthSchema]:
    db_healthy = True
    camera_ids: list[uuid.UUID] = []

    if db_session is not None:
        try:
            repo = CameraRepository(db_session)
            cameras = await repo.list()
            camera_ids = [c.id for c in cameras]
        except Exception:
            db_healthy = False

    system_health = collector.get_system_health(
        db_healthy=db_healthy,
        registered_camera_ids=camera_ids,
    )
    return ApiResponse[SystemHealthSchema](success=True, data=system_health)


@router.get(
    "/api/v1/health/gpu",
    response_model=ApiResponse[GPUHealthSchema],
    summary="Get GPU health and utilization metrics",
)
async def get_gpu_health(
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[GPUHealthSchema]:
    gpu_health = collector.get_gpu_health()
    return ApiResponse[GPUHealthSchema](success=True, data=gpu_health)


@router.get(
    "/api/v1/health/storage",
    response_model=ApiResponse[StorageHealthSchema],
    summary="Get storage utilization metrics",
)
async def get_storage_health(
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[StorageHealthSchema]:
    storage_health = collector.get_storage_health()
    return ApiResponse[StorageHealthSchema](success=True, data=storage_health)


@router.get(
    "/api/v1/health/cameras",
    response_model=ApiResponse[list[CameraHealthSchema]],
    summary="Get health metrics for all registered cameras",
)
async def get_all_cameras_health(
    request: Request,
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
    db_session: AsyncSession | None = Depends(_get_db_session),  # noqa: B008
) -> ApiResponse[list[CameraHealthSchema]]:
    camera_ids: list[uuid.UUID] = []
    if db_session is not None:
        try:
            repo = CameraRepository(db_session)
            cameras = await repo.list()
            camera_ids = [c.id for c in cameras]
        except Exception:
            pass

    # Fallback to active heartbeats if no DB
    if not camera_ids:
        camera_ids = list(collector._camera_heartbeats.keys())

    results = [collector.get_camera_health(cam_id) for cam_id in camera_ids]
    return ApiResponse[list[CameraHealthSchema]](success=True, data=results)


@router.get(
    "/api/v1/cameras/{camera_id}/health",
    response_model=ApiResponse[CameraHealthSchema],
    summary="Get health metrics for a specific camera",
)
async def get_camera_health(
    camera_id: uuid.UUID,
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[CameraHealthSchema]:
    health = collector.get_camera_health(camera_id)
    return ApiResponse[CameraHealthSchema](success=True, data=health)
