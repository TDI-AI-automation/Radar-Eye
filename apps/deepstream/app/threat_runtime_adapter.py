"""ThreatEngineRuntimeAdapter -- RM-11 Phase 2 orchestration layer.

Source: RM-07/RM-09/RM-10 design notes, which named this exact component
("a Threat Engine Runtime Adapter... explicitly deferred until a real
per-frame pipeline exists to feed it (RM-11)"), and the RM-11 Phase 2
design review, which confirmed it as a distinct component from ADR-027's
``RuntimeAdapter``.

Boundary with ``RuntimeAdapter`` (ADR-027): ``RuntimeAdapter`` translates
DeepStream/pyds metadata into repository-native ``FrameObservation`` values
and owns nothing beyond that translation. This class receives only those
plain ``FrameObservation`` values and orchestrates the application services
that turn them into threat decisions -- it never touches ``pyds``, ``Gst``,
or ``GLib``.

Per the Phase 2 design review's Additional Requirement, this class is
orchestration only. It owns no business rules, calibration mathematics,
incident policy, alarm policy, or event definitions -- all of that remains
inside ``CalibrationService``, ``ThreatEngine``, ``IncidentService``, and
``AlarmService`` respectively. ``weapon_mapper``/``uniform_mapper`` are
injected specifically so this class never contains classification logic:
the defaults are the honest "no real classifier exists yet" values (see
their docstrings), never a fabricated guess from a placeholder model's
output (RM-11 Phase 1/2 design reviews, Decision C).

Flow per tracked detection:
    FrameObservation -> CalibrationService.estimate() -> ThreatEngine.ingest()
    -> EscalationSignal routed to IncidentService.handle_escalation() /
       AlarmService.trigger()
    -> ThreatAssessmentEvent / HumanReviewItemCreatedEvent published to EventBus
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.deepstream.app.observations import DetectionObservation, FrameObservation
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationNotFoundError
from services.incident_service.alarm import AlarmService
from services.incident_service.service import IncidentService
from services.threat_engine.engine import ThreatEngine
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.bus import EventBus
from shared.events.types import HumanReviewItemCreatedEvent, ThreatAssessmentEvent

logger = logging.getLogger(__name__)

WeaponMapper = Callable[[DetectionObservation], WeaponType]
UniformMapper = Callable[[DetectionObservation], UniformClass]


def default_weapon_mapper(_detection: DetectionObservation) -> WeaponType:
    """Honest default while PGIE is a placeholder (non-weapon) model: no
    weapon-detection capability exists yet, so NONE -- never a fabricated
    guess. Real class mapping requires an approved weapon-detection model
    (MODEL_REGISTRY.md) and is deliberately not implemented here."""
    return WeaponType.NONE


def default_uniform_mapper(_detection: DetectionObservation) -> UniformClass:
    """Honest default while SGIE is a placeholder (non-uniform) classifier:
    UNKNOWN -- THREAT_ENGINE_SPEC.md's own value for "cannot classify",
    which is the true state here, not a fabricated guess."""
    return UniformClass.UNKNOWN


class ThreatEngineRuntimeAdapter:
    """Coordinates CalibrationService, ThreatEngine, IncidentService, and
    AlarmService for each tracked detection, and routes their outputs onto
    the EventBus. See module docstring for scope boundaries."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        alarm_service: AlarmService,
        weapon_mapper: WeaponMapper = default_weapon_mapper,
        uniform_mapper: UniformMapper = default_uniform_mapper,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._alarm_service = alarm_service
        self._weapon_mapper = weapon_mapper
        self._uniform_mapper = uniform_mapper
        self._threat_engine = ThreatEngine()

    async def on_frame_observation(self, observation: FrameObservation) -> None:
        """Threat assessment requires a stable track -- untracked detections
        (track_id is None; see DetectionObservation's docstring) are
        skipped, matching ThreatEngine's per-track escalation model."""
        for detection in observation.detections:
            if detection.track_id is None:
                continue
            await self._process_detection(observation, detection)

    async def _process_detection(
        self, observation: FrameObservation, detection: DetectionObservation
    ) -> None:
        # Ground-plane contact point convention: bottom-center of the
        # bounding box (CAMERA_CALIBRATION_SPEC.md's ground-plane projection
        # assumes the object touches the ground there, not at its centroid).
        image_x = detection.bbox.left + detection.bbox.width / 2
        image_y = detection.bbox.top + detection.bbox.height

        async with self._session_factory() as session:
            try:
                distance = await CalibrationService(session).estimate(
                    camera_id=observation.camera_id, image_x=image_x, image_y=image_y
                )
            except CalibrationNotFoundError:
                logger.debug(
                    "No calibration for camera %s -- skipping threat assessment "
                    "for track %d (bbox->ground-plane mapping is undefined)",
                    observation.camera_id,
                    detection.track_id,
                )
                return

        assert detection.track_id is not None  # narrowed by on_frame_observation's guard
        results = self._threat_engine.ingest(
            camera_id=observation.camera_id,
            track_id=detection.track_id,
            uniform=self._uniform_mapper(detection),
            weapon_type=self._weapon_mapper(detection),
            zone=distance.zone,
            timestamp=observation.metadata_timestamp,
        )

        for result in results:
            await self._route_result(result)

    async def _route_result(
        self, result: ThreatAssessmentEvent | HumanReviewItemCreatedEvent | EscalationSignal
    ) -> None:
        if isinstance(result, EscalationSignal):
            await self._handle_escalation(result)
        else:
            await self._bus.publish(result)

    async def _handle_escalation(self, signal: EscalationSignal) -> None:
        """INCIDENT_ELIGIBLE and ALARM_ELIGIBLE both resolve to an incident
        first (handle_escalation() is idempotent create-or-return, per
        ADR-025's dedup policy) -- ALARM_ELIGIBLE always arrives at or after
        the corresponding INCIDENT_ELIGIBLE (ADR-021's timers), so this also
        covers the FIRE fast-path where both fire on the same frame."""
        async with self._session_factory() as session:
            incident = await IncidentService(session, self._bus).handle_escalation(
                camera_id=signal.camera_id,
                track_id=signal.track_id,
                threat_level=signal.threat_level,
                reason=signal.reason,
                timestamp=datetime.now(timezone.utc),
            )
            await session.commit()

        if signal.signal_type is EscalationSignalType.ALARM_ELIGIBLE:
            await self._alarm_service.trigger(
                camera_id=signal.camera_id,
                track_id=signal.track_id,
                incident_id=incident.id,
                threat_level=signal.threat_level,
                reason=signal.reason,
            )
