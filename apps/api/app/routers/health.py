"""Health monitoring REST router.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — System Health & Camera Management sections.
Endpoints (paths match the documented contract exactly -- no version prefix;
introducing one is a real API-versioning decision requiring its own ADR):
  - GET /health/system
  - GET /health/gpu
  - GET /health/storage
  - GET /health/recording
  - GET /health/cameras
  - GET /cameras/{camera_id}/health
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.health.collector import HealthCollector
from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraRepository
from shared.schemas.api import ApiResponse
from shared.schemas.camera import CameraHealthSchema
from shared.schemas.health import (
    GPUHealthSchema,
    StorageHealthSchema,
    SystemHealthSchema,
)

router = APIRouter(tags=["Health & Monitoring"])


def _to_camera_health_schema(camera: Camera, *, now: datetime) -> CameraHealthSchema:
    """Observed state is persisted by Camera Runtime (apps.deepstream) to
    the same ``cameras`` row GET /cameras reads -- apps.api and
    apps.deepstream are separate processes and don't share memory, so this
    reads the database directly rather than HealthCollector's in-memory
    camera-heartbeat dict, which nothing in a separate process can ever
    feed."""
    last_frame_age_seconds = (
        max(0.0, (now - camera.last_seen_at).total_seconds())
        if camera.last_seen_at is not None
        else None
    )
    return CameraHealthSchema(
        camera_id=camera.id,
        status=camera.status,  # type: ignore[arg-type]
        fps=camera.fps if camera.status == "CONNECTED" else None,
        last_frame_age_seconds=last_frame_age_seconds,
        latency_ms=camera.latency_ms,
        reconnect_count=camera.reconnect_count,
        last_stream_error=camera.last_stream_error,
    )


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
    "/health/system",
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
    "/health/gpu",
    response_model=ApiResponse[GPUHealthSchema],
    summary="Get GPU health and utilization metrics",
)
async def get_gpu_health(
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[GPUHealthSchema]:
    gpu_health = collector.get_gpu_health()
    return ApiResponse[GPUHealthSchema](success=True, data=gpu_health)


@router.get(
    "/health/storage",
    response_model=ApiResponse[StorageHealthSchema],
    summary="Get storage utilization metrics",
)
async def get_storage_health(
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[StorageHealthSchema]:
    storage_health = collector.get_storage_health()
    return ApiResponse[StorageHealthSchema](success=True, data=storage_health)


@router.get(
    "/health/recording",
    response_model=ApiResponse[StorageHealthSchema],
    summary="Get recording/evidence storage utilization metrics",
)
async def get_recording_health(
    collector: HealthCollector = Depends(_get_collector),  # noqa: B008
) -> ApiResponse[StorageHealthSchema]:
    recording_health = collector.get_recording_health()
    return ApiResponse[StorageHealthSchema](success=True, data=recording_health)


@router.get(
    "/health/cameras",
    response_model=ApiResponse[list[CameraHealthSchema]],
    summary="Get health metrics for all registered cameras",
)
async def get_all_cameras_health(
    db_session: AsyncSession | None = Depends(_get_db_session),  # noqa: B008
) -> ApiResponse[list[CameraHealthSchema]]:
    if db_session is None:
        return ApiResponse[list[CameraHealthSchema]](success=True, data=[])
    cameras = await CameraRepository(db_session).list()
    now = datetime.now(timezone.utc)
    results = [_to_camera_health_schema(camera, now=now) for camera in cameras]
    return ApiResponse[list[CameraHealthSchema]](success=True, data=results)


@router.get(
    "/cameras/{camera_id}/health",
    response_model=ApiResponse[CameraHealthSchema],
    summary="Get health metrics for a specific camera",
)
async def get_camera_health(
    camera_id: uuid.UUID,
    db_session: AsyncSession | None = Depends(_get_db_session),  # noqa: B008
) -> ApiResponse[CameraHealthSchema]:
    camera = await CameraRepository(db_session).get(camera_id) if db_session is not None else None
    if camera is None:
        return ApiResponse[CameraHealthSchema](
            success=True,
            data=CameraHealthSchema(camera_id=camera_id, status="DISCONNECTED"),
        )
    return ApiResponse[CameraHealthSchema](
        success=True, data=_to_camera_health_schema(camera, now=datetime.now(timezone.utc))
    )
