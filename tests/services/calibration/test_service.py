"""Tests for services.calibration.service.CalibrationService.

Source: docs/IMPLEMENTATION_ROADMAP.md's RM-05 acceptance criteria plus the
RM-05 design review's decisions (append-only calibration history, "latest
by created_at wins", no reprojection-quality acceptance gate, real
PostgreSQL required -- no SQLite substitution, per RM-03's testing policy).
"""

from __future__ import annotations

import asyncio

import pytest

from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraCalibrationRepository, CameraRepository
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationNotFoundError, ReferencePoint
from shared.constants.distance_zones import DistanceZone
from shared.events.bus import InProcessEventBus

_POINTS = [
    ReferencePoint(image_x=0, image_y=0, ground_x=0, ground_y=0),
    ReferencePoint(image_x=100, image_y=0, ground_x=25, ground_y=0),
    ReferencePoint(image_x=0, image_y=100, ground_x=0, ground_y=25),
    ReferencePoint(image_x=100, image_y=100, ground_x=25, ground_y=25),
]


def _collecting_handler(sink: list):
    async def handler(event):
        sink.append(event)

    return handler


async def _make_camera(session) -> Camera:
    camera = Camera(name="cam-1", status="CONNECTED")
    return await CameraRepository(session).add(camera)


@pytest.mark.asyncio
class TestCalibrate:
    async def test_persists_calibration_record(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = CalibrationService(db_session)

        calibration = await service.calibrate(
            camera_id=camera.id, reference_points=_POINTS, calibrated_by="installer-1"
        )

        assert calibration.camera_id == camera.id
        assert calibration.calibrated_by == "installer-1"
        stored = await CameraCalibrationRepository(db_session).get(calibration.id)
        assert stored is not None

    async def test_publishes_calibration_updated_event(self, db_session) -> None:
        camera = await _make_camera(db_session)
        bus = InProcessEventBus()
        try:
            updates: list = []
            bus.subscribe("CalibrationUpdatedEvent", _collecting_handler(updates))

            service = CalibrationService(db_session, bus)
            calibration = await service.calibrate(
                camera_id=camera.id, reference_points=_POINTS, calibrated_by="installer-1"
            )

            await asyncio.sleep(0.05)
            assert len(updates) == 1
            assert updates[0].payload.camera_id == camera.id
            assert updates[0].payload.calibration_id == calibration.id
        finally:
            await bus.stop()

    async def test_recalibration_does_not_mutate_or_delete_prior_record(self, db_session) -> None:
        """Roadmap/design-review invariant: calibration history is append-only."""
        camera = await _make_camera(db_session)
        service = CalibrationService(db_session)

        first = await service.calibrate(
            camera_id=camera.id, reference_points=_POINTS, calibrated_by="installer-1"
        )
        second = await service.calibrate(
            camera_id=camera.id, reference_points=_POINTS, calibrated_by="operator-2"
        )

        assert first.id != second.id
        history = await CameraCalibrationRepository(db_session).list_for_camera(camera.id)
        ids = {record.id for record in history}
        assert ids == {first.id, second.id}


@pytest.mark.asyncio
class TestEstimate:
    async def test_uses_latest_calibration_for_camera(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = CalibrationService(db_session)

        await service.calibrate(
            camera_id=camera.id, reference_points=_POINTS, calibrated_by="installer-1"
        )
        # Commit so this calibration gets a distinct created_at from the one
        # below -- func.now() is transaction-start time, so two inserts in
        # the same uncommitted transaction would otherwise tie. In
        # production each calibrate() call is its own request/transaction.
        await db_session.commit()
        # A wider recalibration -- 100px now maps to 50m instead of 25m.
        wider_points = [
            ReferencePoint(image_x=0, image_y=0, ground_x=0, ground_y=0),
            ReferencePoint(image_x=100, image_y=0, ground_x=50, ground_y=0),
            ReferencePoint(image_x=0, image_y=100, ground_x=0, ground_y=50),
            ReferencePoint(image_x=100, image_y=100, ground_x=50, ground_y=50),
        ]
        await service.calibrate(
            camera_id=camera.id, reference_points=wider_points, calibrated_by="operator-2"
        )

        estimate = await service.estimate(camera_id=camera.id, image_x=100, image_y=0)
        assert estimate.distance_meters == pytest.approx(50.0, abs=1e-6)

    async def test_classifies_zone_from_distance(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = CalibrationService(db_session)
        await service.calibrate(
            camera_id=camera.id, reference_points=_POINTS, calibrated_by="installer-1"
        )

        near = await service.estimate(camera_id=camera.id, image_x=10, image_y=0)
        assert near.zone is DistanceZone.ZONE_1

        far = await service.estimate(camera_id=camera.id, image_x=250, image_y=0)
        assert far.zone is DistanceZone.ZONE_3

    async def test_raises_when_camera_never_calibrated(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = CalibrationService(db_session)

        with pytest.raises(CalibrationNotFoundError):
            await service.estimate(camera_id=camera.id, image_x=0, image_y=0)
