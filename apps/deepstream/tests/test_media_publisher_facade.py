"""Tests for apps.deepstream.app.media_publisher.media_publisher.MediaPublisher
-- RM-12 Camera Runtime Step 7.

Pure asyncio -- no DeepStream SDK. Verifies the facade composes both
tiers correctly and that shutdown() reaches both without needing real Gst
objects (uses the same FakePad/RealFutureBridge pattern as
test_media_publisher_base.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from apps.deepstream.app.media_publisher.media_publisher import MediaPublisher


class FakePad:
    def __init__(self) -> None:
        self.probes: dict[int, Callable[..., Any]] = {}
        self._next_id = 1

    def add_probe(self, _probe_type: Any, callback: Callable[..., Any], _user_data: Any) -> int:
        probe_id = self._next_id
        self._next_id += 1
        self.probes[probe_id] = callback
        return probe_id

    def remove_probe(self, probe_id: int) -> None:
        self.probes.pop(probe_id, None)


class FakePipeline:
    def __init__(self) -> None:
        self._pads: dict[uuid.UUID, FakePad] = {}

    def add_camera(self, camera_id: uuid.UUID) -> FakePad:
        pad = FakePad()
        self._pads[camera_id] = pad
        return pad

    def bin_for(self, camera_id: uuid.UUID) -> Any | None:
        bin_ = _FakeBin(self._pads.get(camera_id))
        return bin_ if camera_id in self._pads else None


class _FakeBin:
    def __init__(self, pad: FakePad | None) -> None:
        self._pad = pad

    def get_by_name(self, _name: str) -> _FakeQueue | None:
        return _FakeQueue(self._pad) if self._pad is not None else None


class _FakeQueue:
    def __init__(self, pad: FakePad) -> None:
        self._pad = pad

    def get_static_pad(self, _name: str) -> FakePad:
        return self._pad


@pytest.fixture
def real_future_bridge():
    import concurrent.futures

    class RealFutureBridge:
        def schedule_on_mainloop(self, func: Callable[[], Any]) -> concurrent.futures.Future:
            future: concurrent.futures.Future = concurrent.futures.Future()
            try:
                future.set_result(func())
            except Exception as exc:  # noqa: BLE001 -- propagate, matching AsyncBridge
                future.set_exception(exc)
            return future

    return RealFutureBridge()


@pytest.mark.asyncio
class TestMediaPublisherFacade:
    async def test_owns_one_tier1_and_one_tier2_publisher(self, real_future_bridge) -> None:
        pipeline = FakePipeline()
        media_publisher = MediaPublisher(pipeline, real_future_bridge)

        assert media_publisher.tier1 is not None
        assert media_publisher.tier2 is not None
        assert media_publisher.tier1 is not media_publisher.tier2

    async def test_shutdown_detaches_tier1_cameras(self, real_future_bridge) -> None:
        pipeline = FakePipeline()
        camera_id = uuid.uuid4()
        pad = pipeline.add_camera(camera_id)
        media_publisher = MediaPublisher(pipeline, real_future_bridge)
        await media_publisher.tier1.attach(camera_id)
        assert pad.probes

        await media_publisher.shutdown()

        assert not pad.probes
        assert not media_publisher.tier1.is_attached(camera_id)

    async def test_shutdown_with_nothing_attached_is_a_no_op(self, real_future_bridge) -> None:
        pipeline = FakePipeline()
        media_publisher = MediaPublisher(pipeline, real_future_bridge)
        await media_publisher.shutdown()  # must not raise

    async def test_tiers_are_independent(self, real_future_bridge) -> None:
        """Registering/attaching Tier 1 for a camera must not affect
        Tier 2's own (separate) state for the same camera_id."""
        pipeline = FakePipeline()
        camera_id = uuid.uuid4()
        pipeline.add_camera(camera_id)
        media_publisher = MediaPublisher(pipeline, real_future_bridge)

        await media_publisher.tier1.attach(camera_id)

        assert media_publisher.tier1.is_attached(camera_id)
        assert not media_publisher.tier2.is_attached(camera_id)
