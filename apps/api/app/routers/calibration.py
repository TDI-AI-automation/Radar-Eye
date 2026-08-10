"""Calibration Center REST router -- RM-12 Phase 3 (reads) + Phase 4 (write).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Calibration Center section.
  - GET /calibration/cameras
  - GET /calibration/results
  - GET /calibration/{camera_id}
  - POST /calibration/start (Phase 4, operator-gated, audit-logged)
  - POST /calibration/validate (Phase 4, operator-gated, audit-logged)

``GET /calibration/{camera_id}`` returns the same shape as Camera
Management's ``GET /cameras/{camera_id}/calibration``
(apps.api.app.routers.cameras) -- two contract routes over the same
append-only ``camera_calibrations`` data (docs/DATABASE_SCHEMA.md), one
scoped to a single camera's detail view, one to the dedicated Calibration
Center workflow.

``start``/``validate`` map directly onto ``CalibrationService``'s existing
public interface (services/calibration/service.py) -- ``start`` ==
``calibrate()`` (compute + persist a new homography from operator-supplied
reference points), ``validate`` == ``estimate()`` (project one image point
through the camera's current calibration, returned for the operator to
visually confirm against a known real-world point). Neither route adds new
calibration logic -- this router only translates HTTP <-> the existing
service.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.camera import Camera, CameraCalibration
from apps.api.app.models.user import ROLE_OPERATOR
from apps.api.app.repositories.camera import CameraCalibrationRepository, CameraRepository
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import (
    get_audit_logger,
    get_current_user,
    get_db_session,
    require_role,
)
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationError, ReferencePoint
from shared.schemas.api import ApiResponse
from shared.schemas.calibration import (
    CalibrationStartRequestSchema,
    CalibrationValidateRequestSchema,
    CalibrationValidationResultSchema,
)
from shared.schemas.camera import CameraCalibrationSchema, CameraSchema

router = APIRouter(tags=["Calibration Center"], dependencies=[Depends(get_current_user)])


def _to_camera_schema(camera: Camera) -> CameraSchema:
    return CameraSchema(
        camera_id=camera.id,
        name=camera.name,
        location=camera.location,
        status=camera.status,  # type: ignore[arg-type]
        ai_enabled=camera.ai_enabled,
        recording_enabled=camera.recording_enabled,
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


@router.get("/calibration/cameras", response_model=ApiResponse[list[CameraSchema]])
async def list_calibration_cameras(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[CameraSchema]]:
    cameras = await CameraRepository(session).list()
    return ApiResponse(success=True, data=[_to_camera_schema(c) for c in cameras])


@router.get("/calibration/results", response_model=ApiResponse[list[CameraCalibrationSchema]])
async def list_calibration_results(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[CameraCalibrationSchema]]:
    calibrations = await CameraCalibrationRepository(session).list()
    ordered = sorted(calibrations, key=lambda c: c.created_at, reverse=True)
    return ApiResponse(success=True, data=[_to_calibration_schema(c) for c in ordered])


@router.get("/calibration/{camera_id}", response_model=ApiResponse[CameraCalibrationSchema])
async def get_camera_calibration_result(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraCalibrationSchema]:
    calibration = await CameraCalibrationRepository(session).get_latest_for_camera(camera_id)
    if calibration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No calibration recorded for this camera")
    return ApiResponse(success=True, data=_to_calibration_schema(calibration))


@router.post("/calibration/start", response_model=ApiResponse[CameraCalibrationSchema])
async def start_calibration(
    body: CalibrationStartRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[CameraCalibrationSchema]:
    if await CameraRepository(session).get(body.camera_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    try:
        calibration = await CalibrationService(session).calibrate(
            camera_id=body.camera_id,
            reference_points=[
                ReferencePoint(
                    image_x=p.image_x, image_y=p.image_y, ground_x=p.ground_x, ground_y=p.ground_y
                )
                for p in body.reference_points
            ],
            calibrated_by=str(user.user_id),
        )
    except CalibrationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="START_CALIBRATION",
        resource_type="camera",
        resource_id=str(body.camera_id),
        details={"calibration_id": str(calibration.id)},
    )
    # Built before commit() -- commit() expires ORM attributes by default,
    # and a post-commit attribute access would lazy-load outside the
    # request's async context (MissingGreenlet).
    response_data = _to_calibration_schema(calibration)
    await session.commit()
    return ApiResponse(success=True, data=response_data)


@router.post("/calibration/validate", response_model=ApiResponse[CalibrationValidationResultSchema])
async def validate_calibration(
    body: CalibrationValidateRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[CalibrationValidationResultSchema]:
    try:
        estimate = await CalibrationService(session).estimate(
            camera_id=body.camera_id, image_x=body.image_x, image_y=body.image_y
        )
    except CalibrationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="VALIDATE_CALIBRATION",
        resource_type="camera",
        resource_id=str(body.camera_id),
        details={"distance_meters": estimate.distance_meters, "zone": estimate.zone.value},
    )
    await session.commit()
    return ApiResponse(
        success=True,
        data=CalibrationValidationResultSchema(
            camera_id=body.camera_id,
            distance_meters=estimate.distance_meters,
            zone=estimate.zone,
        ),
    )
