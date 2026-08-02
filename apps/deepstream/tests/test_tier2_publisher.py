"""Tests for apps.deepstream.app.media_publisher.tier2.Tier2Publisher --
RM-12 Camera Runtime Step 7.

Requires the real DeepStream/GStreamer SDK (``nvstreamdemux`` specifically
-- DeepStream-only, not part of generic gst-plugins). Construction/
lifecycle only: nvstreamdemux's actual per-stream demuxing behavior
requires real ``NvDsBatchMeta``-tagged buffers (only streammux produces
those), which is exactly what the real hardware validation exercises
end-to-end -- these tests verify Tier2Publisher's own element
construction/linking/teardown against a real (but unfed) nvstreamdemux
instance, the same "construction-only, no live data needed" scope
test_frame_distributor.py already established for Tier 1.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from apps.deepstream.app.bridge import AsyncBridge  # noqa: E402
from apps.deepstream.app.media_publisher.tier2 import (  # noqa: E402
    Tier2Publisher,
    tier2_queue_element_name,
    tier2_sink_element_name,
)

Gst.init(None)


def _missing_plugins() -> list[str]:
    return [
        name
        for name in ("nvstreamdemux", "queue", "fakesink")
        if Gst.ElementFactory.find(name) is None
    ]


@pytest.fixture(autouse=True)
def _require_deepstream_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer/DeepStream plugin(s) not installed on this machine: {missing}")


class FakeMainLoop:
    def __init__(self) -> None:
        self._stop = threading.Event()

    def run(self) -> None:
        self._stop.wait(timeout=5)

    def quit(self) -> None:
        self._stop.set()


def _immediate_idle_add(callback: Callable[[], bool]) -> int:
    callback()
    return 0


def _make_bridge(loop: asyncio.AbstractEventLoop) -> AsyncBridge:
    bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=_immediate_idle_add)
    bridge.start()
    return bridge


def _make_pipeline_and_demux() -> tuple[Gst.Pipeline, Gst.Element]:
    pipeline = Gst.Pipeline.new("tier2-test-pipeline")
    demux = Gst.ElementFactory.make("nvstreamdemux", "tier2-demux")
    pipeline.add(demux)
    return pipeline, demux


@pytest.mark.asyncio
class TestOnCameraAdded:
    async def test_builds_a_queue_and_sink_named_for_the_camera(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)

        assert pipeline.get_by_name(tier2_queue_element_name(camera_id)) is not None
        assert pipeline.get_by_name(tier2_sink_element_name(camera_id)) is not None

    async def test_queue_is_leaky_and_bounded(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)

        queue = pipeline.get_by_name(tier2_queue_element_name(camera_id))
        assert queue.get_property("leaky") == 2
        assert queue.get_property("max-size-buffers") == 4
        assert queue.get_property("max-size-bytes") == 0
        assert queue.get_property("max-size-time") == 0

    async def test_sink_never_synchronizes_or_blocks(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)

        sink = pipeline.get_by_name(tier2_sink_element_name(camera_id))
        assert sink.get_property("sync") is False
        assert sink.get_property("async") is False

    async def test_demux_pad_is_linked_to_the_queue(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)

        queue = pipeline.get_by_name(tier2_queue_element_name(camera_id))
        queue_sink_pad = queue.get_static_pad("sink")
        assert queue_sink_pad.is_linked()
        assert queue_sink_pad.get_peer().get_parent() == demux

    async def test_different_cameras_get_different_pad_indexes(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_a, pad_index=0)
        publisher.on_camera_added(pipeline, demux, camera_id=camera_b, pad_index=1)

        queue_a = pipeline.get_by_name(tier2_queue_element_name(camera_a))
        queue_b = pipeline.get_by_name(tier2_queue_element_name(camera_b))
        peer_a = queue_a.get_static_pad("sink").get_peer()
        peer_b = queue_b.get_static_pad("sink").get_peer()
        assert peer_a != peer_b  # distinct demux src pads

    async def test_is_idempotent_for_an_already_known_camera(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)
        publisher.on_camera_added(
            pipeline, demux, camera_id=camera_id, pad_index=0
        )  # reconnect path

        # Still exactly one queue/sink pair -- a second call did not build
        # a duplicate branch or raise trying to reuse the name.
        assert pipeline.get_by_name(tier2_queue_element_name(camera_id)) is not None


@pytest.mark.asyncio
class TestOnCameraRemoved:
    async def test_removes_the_branch_elements_from_the_pipeline(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()
        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)

        publisher.on_camera_removed(camera_id)

        assert pipeline.get_by_name(tier2_queue_element_name(camera_id)) is None
        assert pipeline.get_by_name(tier2_sink_element_name(camera_id)) is None

    async def test_is_a_no_op_for_an_unknown_camera(self) -> None:
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        publisher.on_camera_removed(uuid.uuid4())  # must not raise

    async def test_detaches_an_attached_probe_before_teardown(self) -> None:
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()
        publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)
        await publisher.attach(camera_id)
        assert publisher.is_attached(camera_id)

        publisher.on_camera_removed(camera_id)

        assert not publisher.is_attached(camera_id)

    async def test_repeated_add_remove_across_cameras_does_not_leak_names(self) -> None:
        # Distinct cameras get distinct pad_index values -- mirrors
        # DeepStreamPipeline's real, stable per-camera assignment
        # (_camera_pad_index): nvstreamdemux's request pads are never
        # released (see on_camera_removed()'s docstring), so two different
        # cameras must never be assigned the same pad_index within one
        # publisher's lifetime, exactly like the real pipeline guarantees.
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))

        for pad_index in range(3):
            camera_id = uuid.uuid4()
            publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=pad_index)
            publisher.on_camera_removed(camera_id)

        # Bin reaches NULL cleanly afterward -- nothing left half-linked.
        assert pipeline.set_state(Gst.State.NULL) != Gst.StateChangeReturn.FAILURE

    async def test_repeated_add_remove_of_the_same_camera_reuses_the_demux_pad(self) -> None:
        # The actual scenario the "never release" fix targets: a single
        # camera cycling through remove/re-add (lifecycle transitions,
        # RTSP reconnects) many times must reuse its one demux request pad
        # rather than requesting "src_0" again each time -- confirmed here
        # by never seeing a link failure across repeated cycles.
        pipeline, demux = _make_pipeline_and_demux()
        publisher = Tier2Publisher(_make_bridge(asyncio.get_running_loop()))
        camera_id = uuid.uuid4()

        for _ in range(5):
            publisher.on_camera_added(pipeline, demux, camera_id=camera_id, pad_index=0)
            assert pipeline.get_by_name(tier2_queue_element_name(camera_id)) is not None
            publisher.on_camera_removed(camera_id)
            assert pipeline.get_by_name(tier2_queue_element_name(camera_id)) is None

        assert camera_id in publisher._demux_pads  # noqa: SLF001 -- kept, not released
        assert pipeline.set_state(Gst.State.NULL) != Gst.StateChangeReturn.FAILURE
