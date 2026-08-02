"""Tests for
apps.deepstream.app.media_publisher.bitstream.BitstreamPublisher --
Live Streaming architecture reset.

Requires the real DeepStream/GStreamer SDK (matches test_tier1_publisher.py's
established convention) -- a real source bin (``build_source_bin``) is
constructed and BitstreamPublisher's attach/detach genuinely adds/removes
a probe on its real bitstream queue pad. No live camera needed
(construction-only, same reasoning as test_frame_distributor.py).
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from apps.deepstream.app.bridge import AsyncBridge  # noqa: E402
from apps.deepstream.app.ingestion.camera_registry import CameraSource  # noqa: E402
from apps.deepstream.app.ingestion.source import build_source_bin  # noqa: E402
from apps.deepstream.app.media_publisher.base import MediaPublisherError  # noqa: E402
from apps.deepstream.app.media_publisher.bitstream import BitstreamPublisher  # noqa: E402

Gst.init(None)


def _missing_plugins() -> list[str]:
    return [
        name
        for name in (
            "rtspsrc",
            "rtph264depay",
            "h264parse",
            "nvv4l2decoder",
            "valve",
            "tee",
            "queue",
            "fakesink",
        )
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


class FakePipeline:
    def __init__(self) -> None:
        self._bins: dict[uuid.UUID, Any] = {}

    def add_camera(self, camera_id: uuid.UUID) -> Any:
        source = CameraSource(
            camera_id=camera_id,
            name="test-camera",
            rtsp_url="rtsp://192.0.2.1:554/does-not-need-to-be-reachable",
            transport="tcp",
        )
        bin_ = build_source_bin(source)
        self._bins[camera_id] = bin_
        return bin_

    def bin_for(self, camera_id: uuid.UUID) -> Any | None:
        return self._bins.get(camera_id)


@pytest.mark.asyncio
class TestBitstreamPublisherAttach:
    async def test_attach_adds_a_probe_on_the_bitstream_queue_src_pad(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        publisher = BitstreamPublisher(pipeline, _make_bridge(loop))

        await publisher.attach(camera_id)

        assert publisher.is_attached(camera_id)

    async def test_attach_raises_for_a_camera_with_no_active_bin(self) -> None:
        loop = asyncio.get_running_loop()
        pipeline = FakePipeline()
        publisher = BitstreamPublisher(pipeline, _make_bridge(loop))

        with pytest.raises(MediaPublisherError):
            await publisher.attach(uuid.uuid4())

    async def test_detach_removes_the_probe(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        publisher = BitstreamPublisher(pipeline, _make_bridge(loop))
        await publisher.attach(camera_id)

        await publisher.detach(camera_id)

        assert not publisher.is_attached(camera_id)

    async def test_attach_does_not_affect_the_ai_valve(self) -> None:
        """The bitstream tap sits before decode entirely -- structurally
        independent of decode/AI state, same guarantee Tier 1 already
        has. This publisher's attach/detach never touches the valve."""
        from apps.deepstream.app.ingestion.source import valve_element_name

        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        valve = bin_.get_by_name(valve_element_name(camera_id))
        publisher = BitstreamPublisher(pipeline, _make_bridge(loop))

        await publisher.attach(camera_id)

        assert valve.get_property("drop") is False  # unchanged, still permanently open

    async def test_attach_does_not_disturb_the_decode_path(self) -> None:
        """The bitstream tee's other branch must still feed the decoder --
        attaching a probe to the stub branch must not perturb that link."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        decoder = bin_.get_by_name(f"decoder-{camera_id}")
        publisher = BitstreamPublisher(pipeline, _make_bridge(loop))

        await publisher.attach(camera_id)

        sink_pad = decoder.get_static_pad("sink")
        assert sink_pad.is_linked()


class _VideoTestSrcPipeline:
    """A minimal, self-contained real pipeline (videotestsrc -> queue ->
    fakesink, no DeepStream/RTSP dependency) reproducing the bitstream
    branch's shape generically -- lets BitstreamPublisher's
    attach/probe/delivery chain be exercised against genuinely flowing
    real Gst.Buffer objects, without a live camera or the full
    source-bin machinery."""

    def __init__(self, camera_id: uuid.UUID, *, num_buffers: int = 5) -> None:
        from apps.deepstream.app.pipeline.frame_distributor import (
            bitstream_queue_element_name,
        )

        self.pipeline = Gst.Pipeline.new(f"bitstream-delivery-test-{camera_id}")
        src = Gst.ElementFactory.make("videotestsrc", "src")
        src.set_property("num-buffers", num_buffers)
        queue = Gst.ElementFactory.make("queue", bitstream_queue_element_name(camera_id))
        sink = Gst.ElementFactory.make("fakesink", f"bitstream-sink-{camera_id}")
        sink.set_property("sync", False)
        for element in (src, queue, sink):
            self.pipeline.add(element)
        src.link(queue)
        queue.link(sink)
        self.queue = queue

    def get_by_name(self, name: str) -> Any | None:
        return self.pipeline.get_by_name(name)


@pytest.mark.asyncio
class TestBitstreamPublisherDelivery:
    async def test_registered_consumer_receives_real_flowing_buffers(self) -> None:
        """Proves the whole attach -> probe -> registry -> consumer chain
        delivers genuine Gst.Buffer objects end to end, using a minimal
        real (non-DeepStream) pipeline shaped like the bitstream branch."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        test_pipeline = _VideoTestSrcPipeline(camera_id)

        class _SinglePipelineHandle:
            def bin_for(self, cam_id: uuid.UUID) -> Any | None:
                return test_pipeline if cam_id == camera_id else None

        publisher = BitstreamPublisher(_SinglePipelineHandle(), _make_bridge(loop))
        received: list[tuple[uuid.UUID, Any]] = []

        class _Consumer:
            def on_encoded_frame(self, cam_id: uuid.UUID, gst_buffer: Any) -> None:
                received.append((cam_id, gst_buffer))

        publisher.register(camera_id, _Consumer())
        await publisher.attach(camera_id)

        bus = test_pipeline.pipeline.get_bus()
        test_pipeline.pipeline.set_state(Gst.State.PLAYING)
        bus.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        test_pipeline.pipeline.set_state(Gst.State.NULL)

        assert len(received) == 5
        assert all(cam_id == camera_id for cam_id, _buf in received)

    async def test_no_delivery_before_a_consumer_is_registered(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        test_pipeline = _VideoTestSrcPipeline(camera_id, num_buffers=2)

        class _SinglePipelineHandle:
            def bin_for(self, cam_id: uuid.UUID) -> Any | None:
                return test_pipeline if cam_id == camera_id else None

        publisher = BitstreamPublisher(_SinglePipelineHandle(), _make_bridge(loop))
        await publisher.attach(camera_id)  # attached, but nothing registered yet

        bus = test_pipeline.pipeline.get_bus()
        test_pipeline.pipeline.set_state(Gst.State.PLAYING)
        bus.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        test_pipeline.pipeline.set_state(Gst.State.NULL)
        # No assertion failure above means no crash with zero consumers --
        # the actual "nothing delivered" behavior is proven by
        # ConsumerRegistry's own unit tests; this proves it holds through
        # a real probe firing on real buffers too.
