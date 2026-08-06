"""Tests for apps.deepstream.app.ai_runtime.detection.RuntimeAdapter -- Phase 0 scope.

Uses the real InProcessEventBus (RM-04) rather than a fake, matching the
pattern established by tests/shared/test_event_bus.py and
tests/services/calibration/test_service.py.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraRepository
from apps.deepstream.app.ai_runtime.detection import RuntimeAdapter
from apps.deepstream.app.ai_runtime.observations import FrameObservation, build_frame_observation
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from shared.events.bus import InProcessEventBus

_CAMERA = uuid.uuid4()
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def bus():
    instance = InProcessEventBus(queue_maxsize=10, publish_timeout_seconds=0.2)
    yield instance
    await instance.stop()


def _collecting_handler(sink: asyncio.Queue):
    async def handler(event):
        await sink.put(event)

    return handler


@pytest.mark.asyncio
class TestConnectionStatus:
    async def test_unknown_camera_defaults_to_disconnected(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)
        assert adapter.status_for(_CAMERA) == "DISCONNECTED"

    async def test_on_camera_connected_updates_status(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)
        await adapter.on_camera_connected(_CAMERA)
        assert adapter.status_for(_CAMERA) == "CONNECTED"

    async def test_on_camera_reconnecting_updates_status(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)
        await adapter.on_camera_connected(_CAMERA)
        await adapter.on_camera_reconnecting(_CAMERA)
        assert adapter.status_for(_CAMERA) == "RECONNECTING"

    async def test_on_camera_disconnected_updates_status(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)
        await adapter.on_camera_connected(_CAMERA)
        await adapter.on_camera_disconnected(_CAMERA, "RTSP timeout")
        assert adapter.status_for(_CAMERA) == "DISCONNECTED"

    async def test_forget_camera_removes_the_status_entry(self, bus: InProcessEventBus) -> None:
        """Root-cause coverage for the Operator Acceptance Testing
        ownership audit (2026-08-03): _status was write-only -- nothing
        ever removed a deleted camera's entry. status_for() already
        defaults to DISCONNECTED for an unknown camera_id either way, so
        this asserts the dict entry is actually gone (not just that the
        externally-visible read happens to look the same), matching
        RuntimeSupervisor.remove_camera's own leak-proof coverage."""
        camera_id = uuid.uuid4()
        adapter = RuntimeAdapter(bus)
        await adapter.on_camera_connected(camera_id)
        assert camera_id in adapter._status

        adapter.forget_camera(camera_id)

        assert camera_id not in adapter._status
        assert adapter.status_for(camera_id) == "DISCONNECTED"

    async def test_forget_camera_is_a_no_op_for_an_unknown_camera(
        self, bus: InProcessEventBus
    ) -> None:
        adapter = RuntimeAdapter(bus)
        adapter.forget_camera(uuid.uuid4())  # must not raise


@pytest.mark.asyncio
class TestEventPublication:
    async def test_on_camera_connected_publishes_info_system_event(
        self, bus: InProcessEventBus
    ) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_camera_connected(_CAMERA)

        event = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert event.payload.severity == "INFO"
        assert event.payload.source_component == "deepstream"
        assert str(_CAMERA) in event.payload.message

    async def test_on_camera_disconnected_publishes_camera_disconnected_event(
        self, bus: InProcessEventBus
    ) -> None:
        """DEEPSTREAM_PIPELINE_SPEC.md 'Failure Handling' -> 'Camera Failure':
        generate CameraDisconnectedEvent."""
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("CameraDisconnectedEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_camera_disconnected(_CAMERA, "RTSP timeout")

        event = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert event.payload.camera_id == _CAMERA
        assert event.payload.reason == "RTSP timeout"

    async def test_on_pipeline_error_publishes_system_event_with_given_severity(
        self, bus: InProcessEventBus
    ) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_pipeline_error("nvstreammux negotiation failed", severity="CRITICAL")

        event = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert event.payload.severity == "CRITICAL"
        assert event.payload.message == "nvstreammux negotiation failed"


def _make_observation(frame_num: int = 1) -> FrameObservation:
    return build_frame_observation(
        camera_id=_CAMERA,
        frame_num=frame_num,
        ingress_timestamp=_NOW,
        metadata_timestamp=_NOW,
        raw_detections=[(0, "person", 0.9, (0.0, 0.0, 1.0, 1.0), 7, None)],
    )


@pytest.mark.asyncio
class TestFrameObservation:
    """extract_frame_observations itself needs real pyds/NvDsBatchMeta and
    is only verifiable on real DeepStream hardware (see the RM-11 Phase 1
    hardware verification note) -- on_frame_observation's own logic
    (instrumentation recording, last_observation tracking) has no pyds
    dependency and is fully testable here."""

    async def test_records_last_observation(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)
        observation = _make_observation()

        await adapter.on_frame_observation(
            observation, ingress_monotonic_seconds=10.0, metadata_monotonic_seconds=10.02
        )

        assert adapter.last_observation is observation

    async def test_forwards_timing_to_instrumentation(self, bus: InProcessEventBus) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        adapter = RuntimeAdapter(bus, instrumentation=instrumentation)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=10.0, metadata_monotonic_seconds=10.02
        )

        snapshot = instrumentation.snapshot()
        assert snapshot.end_to_end_latency_ms == pytest.approx(20.0)
        assert snapshot.frames_processed == 1

    async def test_without_instrumentation_does_not_raise(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)  # instrumentation=None (default)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )  # must not raise

        assert adapter.last_observation is not None

    async def test_does_not_publish_business_events(self, bus: InProcessEventBus) -> None:
        """ADR-029: AI Runtime never publishes a business decision -- no
        ThreatAssessmentEvent or similar should ever appear."""
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("ThreatAssessmentEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sink.get(), timeout=0.2)


@pytest.mark.asyncio
class TestObservationEventPublication:
    """ADR-029 Phase 3: on_frame_observation publishes ObservationEvent --
    AI Runtime's only outward product besides AI Streaming."""

    async def test_publishes_observation_event(self, bus: InProcessEventBus) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("ObservationEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)
        observation = _make_observation(frame_num=7)

        await adapter.on_frame_observation(
            observation, ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )

        event = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert event.payload.camera_id == _CAMERA
        assert event.payload.frame_num == 7
        assert event.payload.frame_timestamp == _NOW
        assert len(event.payload.detections) == 1
        detection = event.payload.detections[0]
        assert detection.track_id == 7
        assert detection.class_id == 0
        assert detection.label == "person"
        assert detection.confidence == pytest.approx(0.9)
        assert detection.secondary_label is None
        assert detection.extensions is None

    async def test_each_publish_gets_a_fresh_observation_id(self, bus: InProcessEventBus) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("ObservationEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_frame_observation(
            _make_observation(frame_num=1),
            ingress_monotonic_seconds=1.0,
            metadata_monotonic_seconds=1.01,
        )
        await adapter.on_frame_observation(
            _make_observation(frame_num=2),
            ingress_monotonic_seconds=2.0,
            metadata_monotonic_seconds=2.01,
        )

        first = await asyncio.wait_for(sink.get(), timeout=1.0)
        second = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert first.payload.observation_id != second.payload.observation_id
        first_detection_id = first.payload.detections[0].detection_id
        second_detection_id = second.payload.detections[0].detection_id
        assert first_detection_id != second_detection_id

    async def test_records_event_published_instrumentation(self, bus: InProcessEventBus) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        adapter = RuntimeAdapter(bus, instrumentation=instrumentation)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )
        await adapter.on_frame_observation(
            _make_observation(frame_num=2),
            ingress_monotonic_seconds=2.0,
            metadata_monotonic_seconds=2.01,
        )

        assert instrumentation.snapshot().event_throughput_per_sec is not None


@pytest.mark.asyncio
class TestHeartbeatRegistry:
    """RM-11.SIV Unified Heartbeat -- heartbeat is optional (None-safe) and,
    when provided, beats the expected component name on each lifecycle
    event/observation."""

    async def test_heartbeat_is_optional(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)  # no heartbeat= passed

        await adapter.on_camera_connected(_CAMERA)  # must not raise

    async def test_camera_connected_beats_camera_component(self, bus: InProcessEventBus) -> None:
        heartbeat = HeartbeatRegistry()
        adapter = RuntimeAdapter(bus, heartbeat=heartbeat)

        await adapter.on_camera_connected(_CAMERA)

        assert heartbeat.status("camera", stale_after_seconds=5.0).healthy is True

    async def test_frame_observation_beats_runtime_adapter_component(
        self, bus: InProcessEventBus
    ) -> None:
        heartbeat = HeartbeatRegistry()
        adapter = RuntimeAdapter(bus, heartbeat=heartbeat)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )

        status = heartbeat.status("runtime_adapter", stale_after_seconds=5.0)
        assert status.healthy is True
        assert status.counter == 1

    async def test_frame_observation_also_beats_camera_and_pipeline_fps(
        self, bus: InProcessEventBus
    ) -> None:
        """RM-11.SIV real-hardware finding: both must keep beating on every
        frame, not just once at on_camera_connected -- otherwise they go
        stale within their threshold even while frames are actively
        flowing (see runtime_adapter.py's on_frame_observation)."""
        heartbeat = HeartbeatRegistry()
        adapter = RuntimeAdapter(bus, heartbeat=heartbeat)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )

        assert heartbeat.status("camera", stale_after_seconds=5.0).healthy is True
        assert heartbeat.status("pipeline_fps", stale_after_seconds=5.0).healthy is True

    async def test_camera_disconnected_does_not_beat(self, bus: InProcessEventBus) -> None:
        """A disconnect is the opposite of liveness -- it must not extend
        the camera component's healthy window."""
        heartbeat = HeartbeatRegistry()
        adapter = RuntimeAdapter(bus, heartbeat=heartbeat)
        await adapter.on_camera_connected(_CAMERA)
        counter_after_connect = heartbeat.status("camera", stale_after_seconds=5.0).counter

        await adapter.on_camera_disconnected(_CAMERA, "RTSP timeout")

        assert heartbeat.status("camera", stale_after_seconds=5.0).counter == counter_after_connect


@pytest.mark.asyncio
class TestObservedStatePersistence:
    """Camera Connectivity migration: Observed State must be persisted to
    Postgres, event-driven, one write per connection-state transition --
    not per frame. Requires real PostgreSQL (session_factory fixture),
    skips if unreachable."""

    async def test_session_factory_is_optional(self, bus: InProcessEventBus) -> None:
        adapter = RuntimeAdapter(bus)  # no session_factory= passed

        await adapter.on_camera_connected(_CAMERA)  # must not raise

    async def test_on_camera_connected_persists_status_and_last_seen(
        self, db_session, session_factory
    ) -> None:
        camera = await CameraRepository(db_session).add(Camera(name="cam-1", status="DISCONNECTED"))
        await db_session.commit()
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.on_camera_connected(camera.id)

        # A fresh session, not db_session -- db_session's identity map would
        # otherwise return its own stale in-memory copy of `camera` rather
        # than re-querying the row the adapter just wrote via a different
        # session (same fix as this repo's other cross-session tests).
        async with session_factory() as verify_session:
            refreshed = await CameraRepository(verify_session).get(camera.id)
        assert refreshed is not None
        assert refreshed.status == "CONNECTED"
        assert refreshed.last_seen_at is not None

    async def test_on_camera_reconnecting_increments_reconnect_count(
        self, db_session, session_factory
    ) -> None:
        camera = await CameraRepository(db_session).add(Camera(name="cam-1", status="CONNECTED"))
        await db_session.commit()
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.on_camera_reconnecting(camera.id)
        await adapter.on_camera_reconnecting(camera.id)

        async with session_factory() as verify_session:
            refreshed = await CameraRepository(verify_session).get(camera.id)
        assert refreshed is not None
        assert refreshed.status == "RECONNECTING"
        assert refreshed.reconnect_count == 2

    async def test_on_camera_reconnecting_with_reconnect_false_does_not_bump_count(
        self, db_session, session_factory
    ) -> None:
        """A source that was just *added* (not recovering from a failure)
        must not look like it already reconnected -- see runtime.py's
        on_source_connected wiring (Observed-State-accuracy fix)."""
        camera = await CameraRepository(db_session).add(Camera(name="cam-1", status="CONNECTED"))
        await db_session.commit()
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.on_camera_reconnecting(camera.id, reconnect=False)

        async with session_factory() as verify_session:
            refreshed = await CameraRepository(verify_session).get(camera.id)
        assert refreshed is not None
        assert refreshed.status == "RECONNECTING"
        assert refreshed.reconnect_count == 0

    async def test_on_camera_disconnected_persists_status_and_reason(
        self, db_session, session_factory
    ) -> None:
        camera = await CameraRepository(db_session).add(Camera(name="cam-1", status="CONNECTED"))
        await db_session.commit()
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.on_camera_disconnected(camera.id, "RTSP timeout")

        async with session_factory() as verify_session:
            refreshed = await CameraRepository(verify_session).get(camera.id)
        assert refreshed is not None
        assert refreshed.status == "DISCONNECTED"
        assert refreshed.last_stream_error == "RTSP timeout"

    async def test_persist_health_snapshot_writes_fps_and_latency(
        self, db_session, session_factory
    ) -> None:
        camera = await CameraRepository(db_session).add(Camera(name="cam-1", status="CONNECTED"))
        await db_session.commit()
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.persist_health_snapshot(camera.id, fps=24.5, latency_ms=5.1)

        async with session_factory() as verify_session:
            refreshed = await CameraRepository(verify_session).get(camera.id)
        assert refreshed is not None
        assert refreshed.fps == pytest.approx(24.5)
        assert refreshed.latency_ms == pytest.approx(5.1)

    async def test_persistence_for_unknown_camera_does_not_raise(self, session_factory) -> None:
        adapter = RuntimeAdapter(bus=InProcessEventBus(), session_factory=session_factory)

        await adapter.on_camera_connected(uuid.uuid4())  # no matching row -- must not raise
