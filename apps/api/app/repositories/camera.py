from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from apps.api.app.models.camera import Camera, CameraCalibration, CameraStreamProfile
from apps.api.app.repositories.base import Repository


class CameraRepository(Repository[Camera]):
    model = Camera


class CameraStreamProfileRepository(Repository[CameraStreamProfile]):
    model = CameraStreamProfile

    async def get_by_camera_id(self, camera_id: uuid.UUID) -> CameraStreamProfile | None:
        result = await self._session.execute(
            select(CameraStreamProfile).where(CameraStreamProfile.camera_id == camera_id)
        )
        return result.scalar_one_or_none()


class CameraCalibrationRepository(Repository[CameraCalibration]):
    """camera_calibrations is append-only (RM-05 design review): 'current'
    calibration for a camera is defined as the row with the greatest
    created_at for that camera_id. No status/is_current column exists or
    should be added -- history is never mutated or deleted."""

    model = CameraCalibration

    async def get_latest_for_camera(self, camera_id: uuid.UUID) -> CameraCalibration | None:
        result = await self._session.execute(
            select(CameraCalibration)
            .where(CameraCalibration.camera_id == camera_id)
            .order_by(CameraCalibration.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_camera(self, camera_id: uuid.UUID) -> Sequence[CameraCalibration]:
        result = await self._session.execute(
            select(CameraCalibration)
            .where(CameraCalibration.camera_id == camera_id)
            .order_by(CameraCalibration.created_at.desc())
        )
        return result.scalars().all()
