"""Calibration Center REST router -- RM-12 Phase 3 (read routes only).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Calibration Center section.
  - GET /calibration/cameras
  - GET /calibration/results
  - GET /calibration/{camera_id}

``POST /calibration/start`` and ``POST /calibration/validate`` are Phase 4
(mutating, operator-gated) -- not added here.

``GET /calibration/{camera_id}`` returns the same shape as Camera
Management's ``GET /cameras/{camera_id}/calibration``
(apps.api.app.routers.cameras) -- two contract routes over the same
append-only ``camera_calibrations`` data (docs/DATABASE_SCHEMA.md), one
scoped to a single camera's detail view, one to the dedicated Calibration
Center workflow.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.camera import Camera, CameraCalibration
from apps.api.app.repositories.camera import CameraCalibrationRepository, CameraRepository
from apps.api.app.security.dependencies import get_current_user, get_db_session
from shared.schemas.api import ApiResponse
from shared.schemas.camera import CameraCalibrationSchema, CameraSchema

router = APIRouter(tags=["Calibration Center"], dependencies=[Depends(get_current_user)])


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
