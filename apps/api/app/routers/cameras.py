"""Camera Management REST router -- RM-12 Phase 3 (reads) + Phase 4 (write).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Camera Management section.
  - GET /cameras
  - GET /cameras/{camera_id}
  - GET /cameras/{camera_id}/calibration
  - PATCH /cameras/{camera_id} (Phase 4, admin-only, audit-logged)

``GET /cameras/{camera_id}/health`` already exists (RM-09, routers/health.py)
-- not touched here. ``PATCH`` never touches ``camera_stream_profiles``
(RTSP credentials) -- only ``name``/``location``/``status``.

Every read route requires a valid access token (any authenticated role) per
docs/RM-12_IMPLEMENTATION_PLAN.md Phase 3 -- no per-route role gate; the
write route additionally requires the ``admin`` role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.camera import Camera, CameraCalibration
from apps.api.app.models.user import ROLE_ADMIN
from apps.api.app.repositories.camera import CameraCalibrationRepository, CameraRepository
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import (
    get_audit_logger,
    get_current_user,
    get_db_session,
    require_role,
)
from shared.schemas.api import ApiResponse
from shared.schemas.camera import CameraCalibrationSchema, CameraSchema, CameraUpdateRequestSchema

router = APIRouter(tags=["Camera Management"], dependencies=[Depends(get_current_user)])


def _to_camera_schema(camera: Camera) -> CameraSchema:
    return CameraSchema(
        camera_id=camera.id,
        name=camera.name,
        location=camera.location,
        status=camera.status,  # type: ignore[arg-type]
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def _to_calibration_schema(calibration: CameraCalibration) -> CameraCalibrationSchema:
    return CameraCalibrationSchema(
        calibration_id=calibration.id,
        camera_id=calibration.camera_id,
        homography_matrix=calibration.homography_matrix,
        reference_points=calibration.reference_points,
        calibrated_by=calibration.calibrated_by,
        created_at=calibration.created_at,
    )


@router.get("/cameras", response_model=ApiResponse[list[CameraSchema]])
async def list_cameras(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[CameraSchema]]:
    cameras = await CameraRepository(session).list()
    return ApiResponse(success=True, data=[_to_camera_schema(c) for c in cameras])


@router.get("/cameras/{camera_id}", response_model=ApiResponse[CameraSchema])
async def get_camera(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraSchema]:
    camera = await CameraRepository(session).get(camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    return ApiResponse(success=True, data=_to_camera_schema(camera))


@router.get(
    "/cameras/{camera_id}/calibration",
    response_model=ApiResponse[CameraCalibrationSchema],
)
async def get_camera_calibration(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraCalibrationSchema]:
    calibration = await CameraCalibrationRepository(session).get_latest_for_camera(camera_id)
    if calibration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No calibration recorded for this camera")
    return ApiResponse(success=True, data=_to_calibration_schema(calibration))


@router.patch("/cameras/{camera_id}", response_model=ApiResponse[CameraSchema])
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdateRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[CameraSchema]:
    camera = await CameraRepository(session).get(camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(camera, field, value)
    await session.flush()
    # updated_at is server-computed (onupdate=func.now()) -- unlike a
    # server_default populated via RETURNING on INSERT, an UPDATE's
    # onupdate value is not auto-refreshed into the Python object; an
    # explicit refresh() is required before it can be read back.
    await session.refresh(camera)

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="UPDATE_CAMERA",
        resource_type="camera",
        resource_id=str(camera.id),
        details=updates,
    )
    # Build the response before commit() -- commit() expires ORM attributes
    # by default (expire_on_commit), and a post-commit attribute access
    # would trigger an implicit lazy-load outside the request's async
    # context (MissingGreenlet).
    response_data = _to_camera_schema(camera)
    await session.commit()
    return ApiResponse(success=True, data=response_data)
