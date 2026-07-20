from __future__ import annotations

from apps.api.app.models.camera import Camera, CameraCalibration, CameraStreamProfile
from apps.api.app.repositories.base import Repository


class CameraRepository(Repository[Camera]):
    model = Camera


class CameraStreamProfileRepository(Repository[CameraStreamProfile]):
    model = CameraStreamProfile


class CameraCalibrationRepository(Repository[CameraCalibration]):
    model = CameraCalibration
