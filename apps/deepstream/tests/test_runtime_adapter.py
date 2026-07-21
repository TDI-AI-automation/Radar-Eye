"""Tests for apps.deepstream.app.runtime_adapter.RuntimeAdapter -- Phase 0 scope.

Uses the real InProcessEventBus (RM-04) rather than a fake, matching the
pattern established by tests/shared/test_event_bus.py and
tests/services/calibration/test_service.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio

from apps.deepstream.app.runtime_adapter import RuntimeAdapter
from shared.events.bus import InProcessEventBus

_CAMERA = uuid.uuid4()


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
