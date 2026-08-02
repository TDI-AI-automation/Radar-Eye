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
        """Phase 1 explicitly excludes Threat Engine/Incident/Calibration
        integration -- no ThreatAssessmentEvent or similar should appear."""
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("ThreatAssessmentEvent", _collecting_handler(sink))
        adapter = RuntimeAdapter(bus)

        await adapter.on_frame_observation(
            _make_observation(), ingress_monotonic_seconds=1.0, metadata_monotonic_seconds=1.01
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sink.get(), timeout=0.2)


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
