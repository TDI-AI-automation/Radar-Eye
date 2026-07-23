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
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.observations import DetectionObservation, FrameObservation
from apps.deepstream.app.pipeline_trace import PipelineTracer
from apps.deepstream.app.stage_logging import get_audit_logger, get_stage_logger
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationNotFoundError
from services.incident_service.alarm import AlarmService
from services.incident_service.service import IncidentService
from services.threat_engine.engine import ThreatEngine
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.bus import EventBus
from shared.events.payloads import ThreatAssessmentPayload
from shared.events.types import HumanReviewItemCreatedEvent, ThreatAssessmentEvent

logger = logging.getLogger(__name__)
_calibration_logger = get_stage_logger("calibration")
_threat_engine_logger = get_stage_logger("threat_engine")
_audit_logger = get_audit_logger()

_AUDIT_WORTHY_THREAT_LEVELS = (ThreatLevel.HIGH, ThreatLevel.MEDIUM)
"""Only HIGH/MEDIUM reach the operator-facing audit log -- per the RM-11.SIV
approval's own examples ("Threat HIGH", "Threat MEDIUM"). LOW/OBSERVE/ALLY
assessments happen at frame rate and would drown out genuinely major
events; they remain visible on the threat_engine stage logger instead."""

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
        heartbeat: HeartbeatRegistry | None = None,
        tracer: PipelineTracer | None = None,
        instrumentation: PerformanceInstrumentation | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._alarm_service = alarm_service
        self._weapon_mapper = weapon_mapper
        self._uniform_mapper = uniform_mapper
        self._threat_engine = ThreatEngine()
        self._heartbeat = heartbeat
        """RM-11.SIV Unified Heartbeat -- optional so existing/future
        callers that don't need SIV visibility aren't forced to construct
        one. None-safe throughout this class via _beat()."""
        self._tracer = tracer or PipelineTracer(enabled=False)
        self._instrumentation = instrumentation
        """RM-11.SIV Task 7 throughput counters -- optional, None-safe."""

    def _beat(self, component: str, *, reason: str | None = None) -> None:
        if self._heartbeat is not None:
            self._heartbeat.beat(component, reason=reason)

    async def on_frame_observation(self, observation: FrameObservation) -> None:
        """Threat assessment requires a stable track -- untracked detections
        (track_id is None; see DetectionObservation's docstring) are
        skipped, matching ThreatEngine's per-track escalation model."""
        self._beat("threat_runtime_adapter")
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

        self._beat("calibration", reason=f"zone={distance.zone.value}")
        _calibration_logger.debug(
            "Calibration result: camera=%s track=%d zone=%s distance=%.1fm",
            observation.camera_id,
            detection.track_id,
            distance.zone.value,
            distance.distance_meters,
        )
        frame_correlation_id = self._tracer.frame_id(observation.camera_id, observation.frame_num)
        if self._tracer.enabled:
            self._tracer.calibration_result(
                frame_correlation_id,
                zone=distance.zone.value,
                distance_meters=distance.distance_meters,
            )

        assert detection.track_id is not None  # narrowed by on_frame_observation's guard
        results = self._threat_engine.ingest(
            camera_id=observation.camera_id,
            track_id=detection.track_id,
            uniform=self._uniform_mapper(detection),
            weapon_type=self._weapon_mapper(detection),
            zone=distance.zone,
            timestamp=observation.metadata_timestamp,
        )
        self._beat("threat_engine")
        _threat_engine_logger.debug(
            "Threat assessment: camera=%s track=%d results=%d",
            observation.camera_id,
            detection.track_id,
            len(results),
        )

        # FIRE's fast-path can yield both an INCIDENT_ELIGIBLE and an
        # ALARM_ELIGIBLE EscalationSignal for this same detection, and both
        # resolve (idempotently) to the same incident -- tracked here so the
        # "incident" heartbeat beats once per frame it was engaged, not once
        # per signal that happened to touch it.
        beaten_incident_ids: set[uuid.UUID] = set()
        for result in results:
            await self._route_result(result, frame_correlation_id, beaten_incident_ids)

    async def _route_result(
        self,
        result: ThreatAssessmentEvent | HumanReviewItemCreatedEvent | EscalationSignal,
        frame_correlation_id: str,
        beaten_incident_ids: set[uuid.UUID],
    ) -> None:
        if isinstance(result, EscalationSignal):
            await self._handle_escalation(result, frame_correlation_id, beaten_incident_ids)
            return

        if isinstance(result.payload, ThreatAssessmentPayload):
            if self._instrumentation is not None:
                self._instrumentation.record_threat_assessment()
            if self._tracer.enabled:
                self._tracer.threat_assessment(
                    frame_correlation_id,
                    threat_level=result.payload.threat_level.value,
                    rule_id=result.payload.rule_id,
                )
            if result.payload.threat_level in _AUDIT_WORTHY_THREAT_LEVELS:
                _audit_logger.info(
                    "Threat %s: camera=%s track=%d rule=%s",
                    result.payload.threat_level.value,
                    result.payload.camera_id,
                    result.payload.track_id,
                    result.payload.rule_id,
                )
        if self._tracer.enabled:
            self._tracer.event_published(frame_correlation_id, event_type=result.event_type)
        if self._instrumentation is not None:
            self._instrumentation.record_event_published()
        await self._bus.publish(result)

    async def _handle_escalation(
        self,
        signal: EscalationSignal,
        frame_correlation_id: str,
        beaten_incident_ids: set[uuid.UUID],
    ) -> None:
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
        if incident.id not in beaten_incident_ids:
            beaten_incident_ids.add(incident.id)
            self._beat("incident", reason=f"incident_id={incident.id}")
            if self._instrumentation is not None:
                self._instrumentation.record_incident()
        _audit_logger.info(
            "Incident created: incident_id=%s camera=%s track=%d threat_level=%s reason=%s",
            incident.id,
            signal.camera_id,
            signal.track_id,
            signal.threat_level.value,
            signal.reason,
        )
        if self._tracer.enabled:
            self._tracer.incident_created(frame_correlation_id, incident_id=incident.id)

        if signal.signal_type is EscalationSignalType.ALARM_ELIGIBLE:
            await self._alarm_service.trigger(
                camera_id=signal.camera_id,
                track_id=signal.track_id,
                incident_id=incident.id,
                threat_level=signal.threat_level,
                reason=signal.reason,
            )
            self._beat("alarm", reason=f"incident_id={incident.id}")
            if self._instrumentation is not None:
                self._instrumentation.record_alarm()
            _audit_logger.info(
                "Alarm triggered: incident_id=%s camera=%s track=%d threat_level=%s",
                incident.id,
                signal.camera_id,
                signal.track_id,
                signal.threat_level.value,
            )
            if self._tracer.enabled:
                self._tracer.alarm_generated(frame_correlation_id)
