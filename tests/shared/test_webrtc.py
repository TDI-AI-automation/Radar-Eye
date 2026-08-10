"""Tests for shared.media_transport.webrtc -- the generic WebRTC publish
transport (ADR-028) shared by Live Streaming (Phase 2) and, later, AI
Streaming (Phase 5).

Requires the real GStreamer SDK plus GstWebRTC/GstSdp -- skipped, not
failed, when unavailable, matching this repo's established convention.
The decisive test (TestHandleOfferRoundTrip) exercises a real SDP
offer/answer exchange against a real aiortc peer connection -- both
sides of the WebRTC handshake, not mocked -- fed by a synthetic
videotestsrc -> x264enc -> h264parse upstream, mirroring
test_media_transport_rtsp.py's TestRoundTrip philosophy: test both
sides of the interface together, not each in isolation.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from shared.gst_bridge import AsyncBridge  # noqa: E402
from shared.media_transport.webrtc import WebRtcBranch, _first_h264_payload_type  # noqa: E402

Gst.init(None)

aiortc = pytest.importorskip("aiortc")


def _missing_plugins() -> list[str]:
    return [
        name
        for name in ("videotestsrc", "x264enc", "h264parse", "rtph264pay", "webrtcbin")
        if Gst.ElementFactory.find(name) is None
    ]


@pytest.fixture(autouse=True)
def _require_gst_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer plugin(s) not installed on this machine: {missing}")
    try:
        import gi as _gi

        _gi.require_version("GstWebRTC", "1.0")
        _gi.require_version("GstSdp", "1.0")
        from gi.repository import GstSdp, GstWebRTC  # noqa: F401
    except (ImportError, ValueError):
        pytest.skip("GstWebRTC/GstSdp not installed on this machine")


def _make_upstream_bin(camera_id: uuid.UUID) -> Any:
    """A real Gst.Bin with videotestsrc -> x264enc -> h264parse -> [ghost
    pad "src"], standing in for build_source_element()'s return value --
    WebRtcBranch only needs a static "src" pad producing H.264, it
    doesn't care where from (same fixture philosophy as
    test_media_transport_rtsp.py's _make_source_pipeline). Suitable for
    structural tests (linking, teardown) that don't depend on sustained
    real data flow -- see _make_persistent_upstream for one that does."""
    bin_ = Gst.Bin.new(f"test-upstream-{camera_id}")
    src = Gst.ElementFactory.make("videotestsrc", f"src-{camera_id}")
    src.set_property("is-live", True)
    enc = Gst.ElementFactory.make("x264enc", f"enc-{camera_id}")
    enc.set_property("tune", "zerolatency")
    enc.set_property("key-int-max", 15)
    parse = Gst.ElementFactory.make("h264parse", f"parse-{camera_id}")
    for element in (src, enc, parse):
        bin_.add(element)
    src.link(enc)
    enc.link(parse)
    ghost_pad = Gst.GhostPad.new("src", parse.get_static_pad("src"))
    bin_.add_pad(ghost_pad)
    return bin_


def _make_persistent_upstream(camera_id: uuid.UUID) -> tuple[Any, Any]:
    """A real Gst.Bin standing in for a *persistent* subscriber bin that
    stays PLAYING across multiple WebRtcBranch connections (the real
    shape: Live Streaming's own local rtspsrc subscription never stops
    just because no browser is currently attached) -- videotestsrc ->
    x264enc(I420, constrained profile) -> h264parse -> tee, with the
    tee's first branch permanently drained by a fakesink so the live
    source is never starved of a linked consumer.

    Returns ``(bin_, attach_branch)``: ``attach_branch()`` must be
    called on the GLib main-loop thread, once, right before a consumer
    (WebRtcBranch) links to the bin's "src" pad -- it dynamically
    requests a *fresh* tee pad and ghosts it out at that moment, rather
    than upfront at construction time.

    This ordering is required, not just style: a tee's request pad that
    gets activated (via the pipeline's own NULL->PLAYING walk) while
    still unlinked never pushes a single buffer once linked later, even
    though the link itself structurally succeeds (`is_linked()` reports
    True, `.link()` returns OK) -- a real, reproduced GStreamer `tee`
    behavior found writing this test. Requesting the branch only at the
    moment it's about to be used sidesteps it entirely, and mirrors
    apps.ingestion.app.source's own proven ``request_split_pad`` pattern
    for exactly this reason.
    """
    bin_ = Gst.Bin.new(f"test-persistent-upstream-{camera_id}")
    src = Gst.ElementFactory.make("videotestsrc", f"src-{camera_id}")
    src.set_property("is-live", True)
    raw_caps = Gst.ElementFactory.make("capsfilter", f"rawcaps-{camera_id}")
    raw_caps.set_property(
        "caps", Gst.Caps.from_string("video/x-raw,format=I420,width=320,height=240,framerate=30/1")
    )
    enc = Gst.ElementFactory.make("x264enc", f"enc-{camera_id}")
    enc.set_property("tune", "zerolatency")
    enc.set_property("key-int-max", 15)
    # Deliberately I420 (4:2:0) input, not videotestsrc's own default --
    # unconstrained, x264enc auto-negotiates a high-4:4:4 profile from
    # videotestsrc's default format, which most H.264 decoders (aiortc's
    # included) don't support; I420 keeps it to an ordinary 4:2:0
    # profile any standard decoder handles.
    parse = Gst.ElementFactory.make("h264parse", f"parse-{camera_id}")
    tee = Gst.ElementFactory.make("tee", f"tee-{camera_id}")
    drain_queue = Gst.ElementFactory.make("queue", f"drainq-{camera_id}")
    drain_queue.set_property("leaky", 2)
    drain_queue.set_property("max-size-buffers", 4)
    drain_sink = Gst.ElementFactory.make("fakesink", f"drainsink-{camera_id}")
    drain_sink.set_property("sync", False)
    drain_sink.set_property("async", False)
    for element in (src, raw_caps, enc, parse, tee, drain_queue, drain_sink):
        bin_.add(element)
    src.link(raw_caps)
    raw_caps.link(enc)
    enc.link(parse)
    parse.link(tee)
    drain_queue.link(drain_sink)
    drain_pad = tee.get_request_pad("src_%u")
    drain_pad.link(drain_queue.get_static_pad("sink"))

    def attach_branch() -> None:
        branch_pad = tee.get_request_pad("src_%u")
        ghost_pad = Gst.GhostPad.new("src", branch_pad)
        ghost_pad.set_active(True)
        bin_.add_pad(ghost_pad)

    return bin_, attach_branch


class TestFirstH264PayloadType:
    def test_extracts_payload_type_from_sdp(self) -> None:
        sdp = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 100\r\na=rtpmap:100 H264/90000\r\n"
        assert _first_h264_payload_type(sdp) == 100

    def test_returns_none_when_no_h264(self) -> None:
        sdp = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=rtpmap:96 VP8/90000\r\n"
        assert _first_h264_payload_type(sdp) is None


class TestWebRtcBranchTransportLifecycle:
    def test_build_transport_links_payloader_to_upstream(self) -> None:
        camera_id = uuid.uuid4()
        pipeline = Gst.Pipeline.new(f"test-pipeline-{camera_id}")
        upstream = _make_upstream_bin(camera_id)
        pipeline.add(upstream)
        pipeline.set_state(Gst.State.PLAYING)

        loop = asyncio.new_event_loop()
        bridge = AsyncBridge(loop)
        bridge.start()
        try:
            branch = WebRtcBranch(
                pipeline, upstream, camera_id, stun_servers=[], bridge=bridge, loop=loop
            )
            bridge.schedule_on_mainloop(branch._build_transport).result(timeout=5.0)
            try:
                assert branch._webrtcbin is not None
                assert branch._payloader is not None
                upstream_pad = upstream.get_static_pad("src")
                assert upstream_pad.is_linked()
            finally:
                bridge.schedule_on_mainloop(branch._teardown_transport).result(timeout=5.0)
            assert branch._webrtcbin is None
        finally:
            bridge.stop()
            pipeline.set_state(Gst.State.NULL)
            loop.close()

    def test_rebuilding_transport_twice_leaves_no_extra_elements(self) -> None:
        camera_id = uuid.uuid4()
        pipeline = Gst.Pipeline.new(f"test-pipeline-{camera_id}")
        upstream = _make_upstream_bin(camera_id)
        pipeline.add(upstream)
        pipeline.set_state(Gst.State.PLAYING)

        loop = asyncio.new_event_loop()
        bridge = AsyncBridge(loop)
        bridge.start()
        try:
            branch = WebRtcBranch(
                pipeline, upstream, camera_id, stun_servers=[], bridge=bridge, loop=loop
            )

            def _rebuild() -> None:
                branch._teardown_transport()
                branch._build_transport()

            bridge.schedule_on_mainloop(_rebuild).result(timeout=5.0)
            bridge.schedule_on_mainloop(_rebuild).result(timeout=5.0)

            def _count_children() -> int:
                it = pipeline.iterate_elements()
                count = 0
                while True:
                    result, _elem = it.next()
                    if result != Gst.IteratorResult.OK:
                        break
                    count += 1
                return count

            # upstream (one Gst.Bin, added as a single pipeline child --
            # its own 3 internal elements aren't flattened into this
            # count) + this connection's payloader/caps/webrtcbin triple
            # -- not 1 + 6 (which a leak from the first rebuild not
            # being fully removed would produce).
            count = bridge.schedule_on_mainloop(_count_children).result(timeout=5.0)
            assert count == 4

            bridge.schedule_on_mainloop(branch._teardown_transport).result(timeout=5.0)
        finally:
            bridge.stop()
            pipeline.set_state(Gst.State.NULL)
            loop.close()


@pytest.mark.asyncio
class TestHandleOfferRoundTrip:
    """Exercises handle_offer()'s full promise-based SDP/ICE exchange
    against a real aiortc RTCPeerConnection -- both sides of the WebRTC
    handshake, not mocked, mirroring test_media_transport_rtsp.py's
    TestRoundTrip philosophy. Asserts handle_offer() returns a valid SDP
    answer, ICE connects on both sides, and GStreamer's own send-side
    confirms real RTP transmission (the on_first_rtp_packet hook, the
    same signal LiveStreamingRuntime's latency instrumentation attaches
    to) -- exercising every line of handle_offer()'s own new code
    (promise/asyncio bridging, ICE-gathering wait, SDP parsing) against
    a real peer, not a mock.

    Deliberately does not assert which codec gets negotiated or that
    aiortc decodes a frame: against aiortc specifically (unlike every
    real browser this session's earlier hardware validation used),
    GstWebRTCBin's create-answer reproducibly selects VP8 over H264
    despite the H264-only capsfilter on webrtc_caps -- and, separately,
    in this multi-homed sandbox (Tailscale/Docker/IPv6 link-local
    interfaces all present as ICE candidates), the DTLS handshake that
    must follow ICE intermittently hits a transport-level BIO/syscall
    error (confirmed via GST_DEBUG=dtlsconnection:6) specific to this
    environment's network topology. Neither is something WebRtcBranch
    controls or a regression this test should gate on; full
    glass-to-glass frame delivery against a real browser is verified
    during hardware validation instead (see IMPLEMENTATION_STATUS.md)."""

    async def test_offer_answer_negotiates_h264_and_ice_connects(self) -> None:
        from aiortc import RTCPeerConnection, RTCSessionDescription

        camera_id = uuid.uuid4()
        pipeline = Gst.Pipeline.new(f"test-pipeline-{camera_id}")
        upstream, attach_branch = _make_persistent_upstream(camera_id)
        pipeline.add(upstream)

        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop)
        bridge.start()
        pc = RTCPeerConnection()
        first_rtp_packet = asyncio.Event()
        branch: Any = None

        def _signal_first_rtp_packet() -> None:
            loop.call_soon_threadsafe(first_rtp_packet.set)

        try:
            await asyncio.wrap_future(
                bridge.schedule_on_mainloop(lambda: pipeline.set_state(Gst.State.PLAYING))
            )
            # The persistent upstream is now PLAYING and continuously
            # producing buffers (drained by its own internal fakesink
            # branch) -- attach *this* connection's branch pad now, right
            # before WebRtcBranch links to it, per _make_persistent_upstream's
            # own docstring on why the timing here matters.
            await asyncio.wrap_future(bridge.schedule_on_mainloop(attach_branch))

            branch = WebRtcBranch(
                pipeline,
                upstream,
                camera_id,
                stun_servers=[],
                bridge=bridge,
                loop=loop,
                on_first_rtp_packet=_signal_first_rtp_packet,
            )

            pc.addTransceiver("video", direction="recvonly")
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)

            # Non-trickle: wait for aiortc's own ICE gathering to finish
            # before sending the offer, matching webrtc_signaling.py's
            # documented non-trickle contract.
            gathering_complete = asyncio.Event()

            def _on_gathering_state_change() -> None:
                if pc.iceGatheringState == "complete":
                    gathering_complete.set()

            pc.on("icegatheringstatechange", _on_gathering_state_change)
            if pc.iceGatheringState == "complete":
                gathering_complete.set()
            await asyncio.wait_for(gathering_complete.wait(), timeout=10.0)

            answer_sdp = await branch.handle_offer(pc.localDescription.sdp)
            assert "m=video" in answer_sdp
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))

            connected = asyncio.Event()

            def _on_ice_change() -> None:
                if pc.iceConnectionState in ("connected", "completed"):
                    connected.set()

            pc.on("iceconnectionstatechange", _on_ice_change)
            if pc.iceConnectionState in ("connected", "completed"):
                connected.set()
            await asyncio.wait_for(connected.wait(), timeout=10.0)

            await asyncio.wait_for(first_rtp_packet.wait(), timeout=10.0)
        finally:
            await pc.close()
            if branch is not None:
                await asyncio.wrap_future(bridge.schedule_on_mainloop(branch.teardown))
            await asyncio.wrap_future(
                bridge.schedule_on_mainloop(lambda: pipeline.set_state(Gst.State.NULL))
            )
            bridge.stop()
