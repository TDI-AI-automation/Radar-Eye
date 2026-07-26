"""Calibration Service (RM-05).

Owns: computing and persisting camera calibrations (installer calibration
and operator self-service recalibration -- ADR-016 distinguishes these only
by who performs the action, not by a different code path), ground-plane
distance/zone estimation for a calibrated camera, and (per the RM-11 Phase 2
design review's Decision A) the in-memory homography cache that makes
estimate() safe to call on RM-11's per-frame hot path without a database
round-trip on every call.

Does not own: per-frame integration with the DeepStream pipeline (RM-11) or
any interaction with the Threat Engine / Incident Service -- per
EVENT_CONTRACTS.md, CalibrationUpdatedEvent's only consumer is DeepStream,
and DEEPSTREAM_PIPELINE_SPEC.md's Stage 6 (Distance Estimation) is the
in-process integrator that calls estimate() per-frame and feeds the result
to the Threat Engine (Stage 7). That wiring is RM-11's
ThreatEngineRuntimeAdapter; estimate() remains the only public API it calls
-- "No calibration logic shall move into RM-11" (Phase 2 design review).

Cache design (Decision A): a process-wide, module-level cache keyed by
camera_id, holding each camera's current homography matrix. Deliberately
module-level rather than per-instance -- CalibrationService is constructed
per request/session throughout the rest of the repository (see this
module's own tests), and a per-instance cache would be empty on every new
instance, defeating the purpose. A module-level cache is safe because the
single-process runtime topology (RM-11 design review, Decision A) means
every CalibrationService instance in this process already shares the same
Python module state. calibrate() writes the cache immediately (it already
has the freshly computed matrix in hand -- no re-read needed); estimate()
reads from cache on a hit, falling back to the database only on a cold miss
(first estimate() for a camera_id since process start, or after a restart).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.camera import CameraCalibration
from apps.api.app.repositories.camera import CameraCalibrationRepository
from services.calibration import homography as homography_math
from services.calibration.types import CalibrationNotFoundError, DistanceEstimate, ReferencePoint
from shared.constants.distance_zones import DistanceZone
from shared.events.bus import EventBus
from shared.events.payloads import CalibrationUpdatedPayload
from shared.events.types import CalibrationUpdatedEvent

_ZONE_1_MAX_METERS = 20.0
_ZONE_2_MAX_METERS = 50.0


def _classify_zone(distance_meters: float) -> DistanceZone:
    if distance_meters < _ZONE_1_MAX_METERS:
        return DistanceZone.ZONE_1
    if distance_meters < _ZONE_2_MAX_METERS:
        return DistanceZone.ZONE_2
    return DistanceZone.ZONE_3


@dataclass(frozen=True)
class _CachedCalibration:
    calibration_id: uuid.UUID
    homography_matrix: np.ndarray


_cache: dict[uuid.UUID, _CachedCalibration] = {}
"""Module-level, process-wide -- see the module docstring's Cache design note."""


def clear_cache() -> None:
    """Test-only reset of the process-wide cache. Not used by production
    code paths -- calibrate()/estimate() manage cache entries themselves."""
    _cache.clear()


class CalibrationService:
    def __init__(self, session: AsyncSession, bus: EventBus | None = None) -> None:
        self._repo = CameraCalibrationRepository(session)
        self._bus = bus

    async def calibrate(
        self,
        *,
        camera_id: uuid.UUID,
        reference_points: list[ReferencePoint],
        calibrated_by: str | None,
    ) -> CameraCalibration:
        """Compute a homography from reference_points and persist it as a new
        calibration record. Never mutates or deletes prior calibrations for
        this camera -- see CameraCalibrationRepository's docstring."""
        matrix = homography_math.compute_homography(reference_points)

        calibration = CameraCalibration(
            camera_id=camera_id,
            homography_matrix=homography_math.to_json(matrix),
            reference_points={
                "points": [
                    {
                        "image_x": p.image_x,
                        "image_y": p.image_y,
                        "ground_x": p.ground_x,
                        "ground_y": p.ground_y,
                    }
                    for p in reference_points
                ]
            },
            calibrated_by=calibrated_by,
        )
        await self._repo.add(calibration)
        _cache[camera_id] = _CachedCalibration(
            calibration_id=calibration.id, homography_matrix=matrix
        )
        await self._publish_updated(calibration)
        return calibration

    async def estimate(
        self, *, camera_id: uuid.UUID, image_x: float, image_y: float
    ) -> DistanceEstimate:
        """Estimate ground-plane distance and zone for an image point, using
        the camera's current (latest) calibration.

        Raises CalibrationNotFoundError if the camera has never been
        calibrated -- estimate() never guesses a zone from an undefined
        distance (Deterministic Decisions, CLAUDE.md).

        Serves from the in-memory cache when available (see the module
        docstring's Cache design note) -- no database query on a cache hit.
        Safe to call on RM-11's per-frame hot path.
        """
        cached = _cache.get(camera_id)
        if cached is None:
            calibration = await self._repo.get_latest_for_camera(camera_id)
            if calibration is None:
                raise CalibrationNotFoundError(f"no calibration found for camera_id={camera_id}")
            cached = _CachedCalibration(
                calibration_id=calibration.id,
                homography_matrix=homography_math.from_json(calibration.homography_matrix),
            )
            _cache[camera_id] = cached

        ground_x, ground_y = homography_math.project(cached.homography_matrix, image_x, image_y)
        distance_meters = (ground_x**2 + ground_y**2) ** 0.5
        return DistanceEstimate(
            distance_meters=distance_meters, zone=_classify_zone(distance_meters)
        )

    async def _publish_updated(self, calibration: CameraCalibration) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            CalibrationUpdatedEvent(
                event_type="CalibrationUpdatedEvent",
                source="calibration_service",
                payload=CalibrationUpdatedPayload(
                    camera_id=calibration.camera_id,
                    calibration_id=calibration.id,
                ),
            )
        )
