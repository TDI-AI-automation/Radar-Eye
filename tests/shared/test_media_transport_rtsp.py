"""Tests for shared.media_transport.rtsp -- the Media Distribution
Interface's Phase 1 (RTSP) implementation (ADR-028).

Requires the real GStreamer SDK plus GstRtspServer -- skipped, not
failed, when unavailable, matching this repo's established convention.
No live camera needed: ``publish()`` is fed by a synthetic
``videotestsrc -> x264enc -> h264parse`` chain, and the round-trip test
connects a real ``rtspsrc`` (via ``build_rtsp_source_element``) back to
the publisher's own local RTSP server -- a genuine end-to-end exercise
of both sides of the interface, not a mock.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from shared.media_transport.interface import build_source_element  # noqa: E402
from shared.media_transport.rtsp import RtspMediaPublisher  # noqa: E402

Gst.init(None)

_TEST_RTSP_PORT = 18600
_TEST_UDP_PORT_START = 18700


def _missing_plugins() -> list[str]:
    return [
        name
        for name in ("videotestsrc", "x264enc", "h264parse", "rtph264pay", "udpsink", "rtspsrc")
        if Gst.ElementFactory.find(name) is None
    ]


@pytest.fixture(autouse=True)
def _require_gst_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer plugin(s) not installed on this machine: {missing}")
    try:
        import gi as _gi

        _gi.require_version("GstRtspServer", "1.0")
        from gi.repository import GstRtspServer  # noqa: F401
    except (ImportError, ValueError):
        pytest.skip("GstRtspServer not installed on this machine")


def _make_source_pipeline(camera_id: uuid.UUID) -> tuple[Any, Any]:
    """A real Gst.Pipeline with videotestsrc -> x264enc -> h264parse,
    standing in for a camera's real encoded output -- publish() only
    needs a pad that can produce H.264, it doesn't care where from."""
    pipeline = Gst.Pipeline.new(f"test-pipeline-{camera_id}")
    src = Gst.ElementFactory.make("videotestsrc", f"src-{camera_id}")
    src.set_property("is-live", True)
    enc = Gst.ElementFactory.make("x264enc", f"enc-{camera_id}")
    enc.set_property("tune", "zerolatency")
    enc.set_property("key-int-max", 15)
    # x264enc's own default GOP is 250 frames (~8s at 30fps) -- rtph264depay
    # only starts producing output once it has seen a real keyframe, so a
    # short GOP here keeps this test fast and comfortably inside its own
    # timeout, matching the real camera's own much shorter GOP in practice.
    parse = Gst.ElementFactory.make("h264parse", f"parse-{camera_id}")
    for element in (src, enc, parse):
        pipeline.add(element)
    src.link(enc)
    enc.link(parse)
    return pipeline, parse


class TestPublish:
    def test_publish_returns_an_rtsp_endpoint(self) -> None:
        camera_id = uuid.uuid4()
        pipeline, parse = _make_source_pipeline(camera_id)
        publisher = RtspMediaPublisher(
            pipeline,
            host="127.0.0.1",
            rtsp_port=_TEST_RTSP_PORT,
            udp_port_range_start=_TEST_UDP_PORT_START,
            subsystem="ingestion",
        )
        publisher.start()
        try:
            endpoint = publisher.publish(camera_id, parse.get_static_pad("src"))
            assert endpoint.camera_id == camera_id
            assert endpoint.subsystem == "ingestion"
            assert endpoint.transport == "rtsp"
            assert endpoint.address == f"rtsp://127.0.0.1:{_TEST_RTSP_PORT}/{camera_id}"
        finally:
            publisher.stop()

    def test_publish_is_idempotent(self) -> None:
        camera_id = uuid.uuid4()
        pipeline, parse = _make_source_pipeline(camera_id)
        publisher = RtspMediaPublisher(
            pipeline,
            host="127.0.0.1",
            rtsp_port=_TEST_RTSP_PORT + 1,
            udp_port_range_start=_TEST_UDP_PORT_START + 10,
            subsystem="ingestion",
        )
        publisher.start()
        try:
            first = publisher.publish(camera_id, parse.get_static_pad("src"))
            second = publisher.publish(camera_id, parse.get_static_pad("src"))
            assert first == second
        finally:
            publisher.stop()

    def test_unpublish_then_publish_again_succeeds(self) -> None:
        camera_id = uuid.uuid4()
        pipeline, parse = _make_source_pipeline(camera_id)
        publisher = RtspMediaPublisher(
            pipeline,
            host="127.0.0.1",
            rtsp_port=_TEST_RTSP_PORT + 2,
            udp_port_range_start=_TEST_UDP_PORT_START + 20,
            subsystem="ingestion",
        )
        publisher.start()
        try:
            publisher.publish(camera_id, parse.get_static_pad("src"))
            publisher.unpublish(camera_id)
            publisher.unpublish(camera_id)  # idempotent -- must not raise
            endpoint = publisher.publish(camera_id, parse.get_static_pad("src"))
            assert endpoint.camera_id == camera_id
        finally:
            publisher.stop()


class TestBuildSourceElement:
    def test_returns_a_bin_with_a_src_ghost_pad(self) -> None:
        from shared.media_transport.interface import MediaEndpoint

        endpoint = MediaEndpoint(
            camera_id=uuid.uuid4(),
            subsystem="ingestion",
            transport="rtsp",
            address="rtsp://127.0.0.1:8600/does-not-need-to-be-reachable",
        )
        bin_ = build_source_element(endpoint)
        assert bin_.get_static_pad("src") is not None

    def test_unknown_transport_raises(self) -> None:
        from shared.media_transport.interface import MediaEndpoint

        endpoint = MediaEndpoint(
            camera_id=uuid.uuid4(), subsystem="ingestion", transport="shm", address="whatever"
        )
        with pytest.raises(NotImplementedError, match="shm"):
            build_source_element(endpoint)


class TestRoundTrip:
    def test_a_real_subscriber_receives_the_published_stream(self) -> None:
        """The decisive test: publish a synthetic encoded stream, then
        connect a real rtspsrc-based consumer (built the same way any
        real subsystem would, via build_source_element()) back to the
        publisher's own local RTSP server, and confirm a real buffer
        arrives -- exercising both sides of the Media Distribution
        Interface together, not just each in isolation.

        Requires a running GLib main loop -- GstRtspServer only
        services client connections while its GMainContext is being
        iterated, exactly the job shared.gst_bridge.AsyncBridge does
        for every real caller. This test runs its own, matching what
        any real subsystem always has."""
        from gi.repository import GLib  # noqa: PLC0415

        mainloop = GLib.MainLoop()
        mainloop_thread = threading.Thread(target=mainloop.run, daemon=True)
        mainloop_thread.start()
        try:
            self._run(uuid.uuid4())
        finally:
            mainloop.quit()
            mainloop_thread.join(timeout=2.0)

    def _run(self, camera_id: uuid.UUID) -> None:
        publish_pipeline, parse = _make_source_pipeline(camera_id)
        publisher = RtspMediaPublisher(
            publish_pipeline,
            host="127.0.0.1",
            rtsp_port=_TEST_RTSP_PORT + 3,
            udp_port_range_start=_TEST_UDP_PORT_START + 30,
            subsystem="ingestion",
        )
        publisher.start()
        try:
            endpoint = publisher.publish(camera_id, parse.get_static_pad("src"))
            publish_pipeline.set_state(Gst.State.PLAYING)

            consumer_pipeline = Gst.Pipeline.new("test-consumer")
            source_bin = build_source_element(endpoint)
            sink = Gst.ElementFactory.make("fakesink", "sink")
            sink.set_property("sync", False)
            consumer_pipeline.add(source_bin)
            consumer_pipeline.add(sink)
            source_bin.get_static_pad("src").link(sink.get_static_pad("sink"))

            received = threading.Event()

            def _on_buffer(_pad: Any, _info: Any) -> Any:
                received.set()
                return Gst.PadProbeReturn.OK

            sink.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, _on_buffer)

            consumer_pipeline.set_state(Gst.State.PLAYING)
            try:
                assert received.wait(timeout=10.0), "consumer never received a published buffer"
            finally:
                consumer_pipeline.set_state(Gst.State.NULL)
        finally:
            publish_pipeline.set_state(Gst.State.NULL)
            publisher.stop()
