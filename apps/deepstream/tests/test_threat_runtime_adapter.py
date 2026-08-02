"""Tests for apps.deepstream.app.ai_runtime.threat_bridge.ThreatEngineRuntimeAdapter.

Mapper functions and the untracked-detection skip are pure/mockable and
tested without a database. Full orchestration (Calibration -> ThreatEngine
-> Incident/Alarm -> EventBus) requires real PostgreSQL (RM-03's testing
policy, no SQLite substitution) via this package's session_factory fixture
-- skips if unreachable, same as every other DB-dependent test in this repo.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraRepository
from apps.deepstream.app.ai_runtime.observations import (
    BoundingBox,
    DetectionObservation,
    FrameObservation,
)
from apps.deepstream.app.ai_runtime.threat_bridge import (
    ThreatEngineRuntimeAdapter,
    default_uniform_mapper,
    default_weapon_mapper,
)
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from services.calibration.service import CalibrationService
from services.calibration.types import ReferencePoint
from services.incident_service.alarm import AlarmService
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.bus import InProcessEventBus

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CALIBRATION_POINTS = [
    ReferencePoint(image_x=0, image_y=0, ground_x=0, ground_y=0),
    ReferencePoint(image_x=100, image_y=0, ground_x=25, ground_y=0),
    ReferencePoint(image_x=0, image_y=100, ground_x=0, ground_y=25),
    ReferencePoint(image_x=100, image_y=100, ground_x=25, ground_y=25),
]


def _detection(*, track_id: int | None = 7, label: str = "car") -> DetectionObservation:
    return DetectionObservation(
        class_id=0,
        label=label,
        confidence=0.9,
        bbox=BoundingBox(left=0.0, top=0.0, width=10.0, height=10.0),
        track_id=track_id,
    )


def _observation(
    camera_id: uuid.UUID, *, detections: list[DetectionObservation]
) -> FrameObservation:
    return FrameObservation(
        camera_id=camera_id,
        frame_num=1,
        ingress_timestamp=_NOW,
        metadata_timestamp=_NOW,
        detections=tuple(detections),
    )


def _collecting_handler(sink: asyncio.Queue):
    async def handler(event):
        await sink.put(event)

    return handler


class TestDefaultMappers:
    def test_weapon_mapper_is_none(self) -> None:
        assert default_weapon_mapper(_detection()) is WeaponType.NONE

    def test_uniform_mapper_is_unknown(self) -> None:
        assert default_uniform_mapper(_detection()) is UniformClass.UNKNOWN


@pytest.mark.asyncio
class TestSkipsUntrackedDetections:
    async def test_only_processes_detections_with_a_track_id(self) -> None:
        bus = InProcessEventBus()
        try:
            adapter = ThreatEngineRuntimeAdapter(
                session_factory=AsyncMock(), bus=bus, alarm_service=AlarmService(bus=bus)
            )
            adapter._process_detection = AsyncMock()  # type: ignore[method-assign] # noqa: SLF001 -- spy for this test only

            observation = _observation(
                uuid.uuid4(),
                detections=[_detection(track_id=None), _detection(track_id=1)],
            )
            await adapter.on_frame_observation(observation)

            assert adapter._process_detection.await_count == 1  # noqa: SLF001
        finally:
            await bus.stop()


async def _make_camera(session) -> Camera:
    return await CameraRepository(session).add(Camera(name="cam-1", status="CONNECTED"))


@pytest.mark.asyncio
class TestOrchestration:
    async def test_uncalibrated_camera_produces_no_events(self, session_factory) -> None:
        async with session_factory() as session:
            camera = await _make_camera(session)
            await session.commit()

        bus = InProcessEventBus()
        try:
            sink: asyncio.Queue = asyncio.Queue()
            bus.subscribe("ThreatAssessmentEvent", _collecting_handler(sink))
            adapter = ThreatEngineRuntimeAdapter(
                session_factory=session_factory, bus=bus, alarm_service=AlarmService(bus=bus)
            )

            observation = _observation(camera.id, detections=[_detection()])
            await adapter.on_frame_observation(observation)

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(sink.get(), timeout=0.2)
        finally:
            await bus.stop()

    async def test_fire_detection_creates_incident_and_triggers_alarm(
        self, session_factory
    ) -> None:
        """FIRE bypasses debounce entirely (THREAT_ENGINE_SPEC.md) -- one
        frame is enough to reach both IncidentService and AlarmService."""
        async with session_factory() as session:
            camera = await _make_camera(session)
            await CalibrationService(session).calibrate(
                camera_id=camera.id,
                reference_points=_CALIBRATION_POINTS,
                calibrated_by="installer-1",
            )
            await session.commit()

        bus = InProcessEventBus()
        try:
            threat_sink: asyncio.Queue = asyncio.Queue()
            incident_sink: asyncio.Queue = asyncio.Queue()
            bus.subscribe("ThreatAssessmentEvent", _collecting_handler(threat_sink))
            bus.subscribe("IncidentCreatedEvent", _collecting_handler(incident_sink))

            alarm_service = AlarmService(bus=bus)
            adapter = ThreatEngineRuntimeAdapter(
                session_factory=session_factory,
                bus=bus,
                alarm_service=alarm_service,
                weapon_mapper=lambda _d: WeaponType.FIRE,
            )

            observation = _observation(camera.id, detections=[_detection(track_id=99)])
            await adapter.on_frame_observation(observation)

            threat_event = await asyncio.wait_for(threat_sink.get(), timeout=1.0)
            assert threat_event.payload.threat_level.value == "HIGH"

            incident_event = await asyncio.wait_for(incident_sink.get(), timeout=1.0)
            assert incident_event.payload.camera_id == camera.id

            active_alarms = alarm_service.get_active_alarms()
            assert len(active_alarms) == 1
            assert active_alarms[0].incident_id == incident_event.payload.incident_id
        finally:
            await bus.stop()

    async def test_full_chain_beats_expected_heartbeat_components(self, session_factory) -> None:
        """RM-11.SIV Unified Heartbeat: calibration/threat_engine/incident/
        alarm each beat once the FIRE fast-path runs the full chain."""
        async with session_factory() as session:
            camera = await _make_camera(session)
            await CalibrationService(session).calibrate(
                camera_id=camera.id,
                reference_points=_CALIBRATION_POINTS,
                calibrated_by="installer-1",
            )
            await session.commit()

        bus = InProcessEventBus()
        try:
            incident_sink: asyncio.Queue = asyncio.Queue()
            bus.subscribe("IncidentCreatedEvent", _collecting_handler(incident_sink))

            heartbeat = HeartbeatRegistry()
            instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
            adapter = ThreatEngineRuntimeAdapter(
                session_factory=session_factory,
                bus=bus,
                alarm_service=AlarmService(bus=bus),
                weapon_mapper=lambda _d: WeaponType.FIRE,
                heartbeat=heartbeat,
                instrumentation=instrumentation,
            )

            observation = _observation(camera.id, detections=[_detection(track_id=42)])
            await adapter.on_frame_observation(observation)
            await asyncio.wait_for(incident_sink.get(), timeout=1.0)

            for component in (
                "threat_runtime_adapter",
                "calibration",
                "threat_engine",
                "incident",
                "alarm",
            ):
                status = heartbeat.status(component, stale_after_seconds=5.0)
                assert status.healthy is True, f"{component} did not beat"
                assert status.counter == 1

            # RM-11.SIV Task 7: instrumentation wiring exercised through the
            # real orchestration path (rate math itself is unit-tested
            # SDK-free in test_instrumentation.py -- a single frame can't
            # produce a rate, since _RollingRateCounter needs 2+ samples).
            snapshot = instrumentation.snapshot()
            assert snapshot.threat_throughput_per_sec is None
            assert snapshot.event_throughput_per_sec is None
        finally:
            await bus.stop()

    async def test_unknown_uniform_creates_human_review_not_incident(self, session_factory) -> None:
        """Default mappers (UNKNOWN uniform) route to HUMAN_REVIEW, which
        THREAT_ENGINE_SPEC.md says never creates an incident."""
        async with session_factory() as session:
            camera = await _make_camera(session)
            await CalibrationService(session).calibrate(
                camera_id=camera.id,
                reference_points=_CALIBRATION_POINTS,
                calibrated_by="installer-1",
            )
            await session.commit()

        bus = InProcessEventBus()
        try:
            review_sink: asyncio.Queue = asyncio.Queue()
            incident_sink: asyncio.Queue = asyncio.Queue()
            bus.subscribe("HumanReviewItemCreatedEvent", _collecting_handler(review_sink))
            bus.subscribe("IncidentCreatedEvent", _collecting_handler(incident_sink))

            adapter = ThreatEngineRuntimeAdapter(
                session_factory=session_factory, bus=bus, alarm_service=AlarmService(bus=bus)
            )

            observation = _observation(camera.id, detections=[_detection(track_id=5)])
            await adapter.on_frame_observation(observation)

            review_event = await asyncio.wait_for(review_sink.get(), timeout=1.0)
            assert review_event.payload.camera_id == camera.id

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(incident_sink.get(), timeout=0.2)
        finally:
            await bus.stop()
