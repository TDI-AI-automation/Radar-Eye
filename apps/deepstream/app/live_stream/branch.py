"""CameraWebRtcBranch -- one camera's permanent WebRTC publish pipeline.

Built once when a camera connects, torn down once when it disconnects --
never rebuilt on a future source switch. See ``apps/deepstream/app/
live_stream/__init__.py``'s module docstring for the full branch diagram
and the architectural reasoning (transport-only, decode-free/encode-free
passthrough of the camera's original H.264 bitstream).

Element construction/linking must run on the GLib main-loop thread
(``AsyncBridge.schedule_on_mainloop``, the same discipline every other
pipeline-mutating component in this codebase follows) -- ``build()`` and
``teardown()`` are synchronous and are only ever called already
scheduled there by ``manager.py``. ``handle_offer()`` is the one
``async`` entry point: SDP/ICE negotiation is a multi-step, promise-based
GLib exchange, bridged to asyncio the same way ``AsyncBridge`` bridges
every other GLib callback in this codebase.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import LiveStreamSettings
from apps.deepstream.app.live_stream.consumer import BitstreamAppsrcBridge
from apps.deepstream.app.pipeline.frame_distributor import bitstream_queue_element_name
from apps.deepstream.app.stage_logging import get_stage_logger

logger = logging.getLogger(__name__)
_live_stream_logger = get_stage_logger("live_stream")


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    gi.require_version("GstWebRTC", "1.0")
    gi.require_version("GstSdp", "1.0")
    from gi.repository import Gst, GstSdp, GstWebRTC  # noqa: PLC0415

    return Gst, GstWebRTC, GstSdp


class CameraWebRtcBranch:
    def __init__(
        self,
        pipeline: Any,
        camera_id: uuid.UUID,
        camera_name: str,
        *,
        live_settings: LiveStreamSettings,
        appsrc_bridge: BitstreamAppsrcBridge,
        bridge: AsyncBridge,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._pipeline = pipeline
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._settings = live_settings
        self._appsrc_bridge = appsrc_bridge
        self._bridge = bridge
        self._loop = loop

        self._elements: list[Any] = []
        self._appsrc: Any = None
        self._input_selector: Any = None
        self._raw_selector_pad: Any = None
        self._payloader: Any = None
        self._webrtcbin: Any = None
        self._rtp_probe_target: Any = None
        self._rtp_probe_id: int | None = None
        self._first_rtp_packet_seen = False
        self._ice_gathering_complete = False

    # -- Construction (GLib main-loop thread only) ---------------------

    def build(self) -> None:
        """Constructs and links the full per-camera branch. Raises
        immediately on any construction/link failure, matching
        VisualizationPipelineBuilder's own "fail fast, never return a
        half-built branch" discipline."""
        Gst, _GstWebRTC, _GstSdp = _import_gst()

        raw_src = self._raw_input_chain(Gst)

        # input-selector is built with a single input already -- a future
        # second (annotated) input can be added later as a purely
        # additive change (request a new sink pad, link a new upstream
        # branch) without ever touching anything downstream of the
        # selector (rtph264pay/webrtcbin/the already-negotiated peer
        # connection). See __init__.py's module docstring.
        selector = self._make(Gst, "input-selector", f"live-selector-{self._camera_id}")
        self._pipeline.add(selector)
        self._elements.append(selector)
        self._raw_selector_pad = selector.get_request_pad("sink_%u")
        self._link_pads(raw_src.get_static_pad("src"), self._raw_selector_pad)
        selector.set_property("active-pad", self._raw_selector_pad)
        self._input_selector = selector

        payloader = self._make(Gst, "rtph264pay", f"live-pay-{self._camera_id}")
        payloader.set_property("pt", 96)  # placeholder -- reset to whatever
        # the browser's offer actually negotiates, in handle_offer() below,
        # before any real data flows (see BitstreamPublisher attach-timing
        # note in manager.py). 96 is never itself sent over the wire.
        payloader.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe
        self._pipeline.add(payloader)
        self._elements.append(payloader)
        self._link(selector, payloader)
        self._payloader = payloader

        # webrtcbin's create-answer runs before any real data has ever
        # flowed through this branch (negotiation must complete before the
        # peer connection exists for rtph264pay to push into) -- so it has
        # no caps information on its sink pad yet unless told explicitly.
        # Without this, webrtcbin falls back to its own default codec
        # preference (observed: VP8) instead of H264, and negotiation
        # degrades to "inactive". This capsfilter is the fix: it declares
        # the codec (H264) webrtcbin should expect.
        #
        # Deliberately no ``payload=`` field here (hardware-confirmed):
        # a browser's offer picks its own dynamic payload type number for
        # H264 (aiortc/most browsers use 99-127, not necessarily 96), and
        # GStreamer's compatible-transceiver search requires an *exact*
        # payload-number match when both sides declare a fixed value --
        # rtph264pay's own pad template already advertises the full
        # dynamic range (payload=[96,127]; confirmed via gst-inspect), so
        # leaving this field unconstrained lets it intersect with whatever
        # number the browser's offer actually uses.
        webrtc_caps = self._make(Gst, "capsfilter", f"live-webrtc-caps-{self._camera_id}")
        webrtc_caps.set_property(
            "caps",
            Gst.Caps.from_string(
                "application/x-rtp,media=video,encoding-name=H264,clock-rate=90000"
            ),
        )
        self._pipeline.add(webrtc_caps)
        self._elements.append(webrtc_caps)
        self._link(payloader, webrtc_caps)

        self._rtp_probe_target = webrtc_caps.get_static_pad("src")
        self._rtp_probe_id = self._rtp_probe_target.add_probe(
            Gst.PadProbeType.BUFFER, self._on_rtp_buffer
        )

        webrtcbin = self._make(Gst, "webrtcbin", f"live-webrtc-{self._camera_id}")
        webrtcbin.set_property("bundle-policy", "max-bundle")
        for stun_server in self._settings.stun_servers:
            webrtcbin.set_property("stun-server", stun_server)
        self._pipeline.add(webrtcbin)
        self._elements.append(webrtcbin)
        webrtcbin.connect("notify::ice-gathering-state", self._on_ice_gathering_state_changed)
        webrtcbin.connect("notify::ice-connection-state", self._on_webrtc_state_changed)
        webrtcbin.connect("notify::connection-state", self._on_webrtc_state_changed)

        webrtc_sink_pad = webrtcbin.get_request_pad("sink_%u")
        if webrtc_sink_pad is None:
            raise RuntimeError(f"Failed to request webrtcbin sink pad for camera {self._camera_id}")
        self._link_pads(webrtc_caps.get_static_pad("src"), webrtc_sink_pad)
        transceiver = webrtc_sink_pad.get_property("transceiver")
        if transceiver is not None:
            # Server only ever sends video for this feature -- never
            # receives anything back from the browser.
            transceiver.set_property("direction", _GstWebRTC.WebRTCRTPTransceiverDirection.SENDONLY)
        self._webrtcbin = webrtcbin

        for element in self._elements:
            element.sync_state_with_parent()

    def _raw_input_chain(self, Gst: Any) -> Any:
        """appsrc, fed directly by ``BitstreamAppsrcBridge`` with the
        camera's original, already-encoded H.264 access units -- no
        decode, no convert, no re-encode. The appsrc's own caps (set once
        the first access unit is observed -- see ``consumer.py``) are the
        camera's real negotiated H.264 caps, so no additional capsfilter
        is needed here: whatever ``h264parse`` actually produced is
        exactly what flows into ``input-selector``."""
        appsrc = self._make(Gst, "appsrc", f"live-raw-src-{self._camera_id}")
        appsrc.set_property("is-live", True)
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("block", False)
        self._pipeline.add(appsrc)
        self._elements.append(appsrc)
        self._appsrc = appsrc

        queue = self._pipeline.get_by_name(bitstream_queue_element_name(self._camera_id))
        bitstream_src_pad = queue.get_static_pad("src") if queue is not None else None
        self._appsrc_bridge.set_appsrc(self._camera_id, appsrc, bitstream_src_pad)
        return appsrc

    # -- Transport-level logging -----------------------------------------

    def _on_rtp_buffer(self, _pad: Any, _info: Any) -> Any:
        """Runs on a GStreamer streaming thread (pad probe)."""
        Gst, _GstWebRTC, _GstSdp = _import_gst()
        if not self._first_rtp_packet_seen:
            self._first_rtp_packet_seen = True
            _live_stream_logger.info(
                "RTP packet transmitted: first RTP packet for camera %s", self._camera_id
            )
        else:
            _live_stream_logger.debug("RTP packet transmitted: camera %s", self._camera_id)
        return Gst.PadProbeReturn.OK

    def _on_webrtc_state_changed(self, webrtcbin: Any, pspec: Any) -> None:
        state = webrtcbin.get_property(pspec.name)
        _live_stream_logger.info(
            "WebRTC state changed: camera %s, %s=%s", self._camera_id, pspec.name, state
        )

    # -- Signaling (async) ----------------------------------------------

    async def handle_offer(self, sdp_offer_text: str) -> str:
        """Given a browser's non-trickle SDP offer (ICE already fully
        gathered client-side), returns the complete answer SDP (this
        server's ICE also fully gathered) as plain text. One call per
        browser connection -- no renegotiation is ever needed afterward:
        this stage never changes the webrtcbin/payloader/track after the
        connection is built."""
        if self._webrtcbin is None:
            raise RuntimeError(f"WebRTC branch not built for camera {self._camera_id}")
        Gst, GstWebRTC, GstSdp = _import_gst()

        # The browser's offer picks its own dynamic RTP payload type number
        # for H264 (see build()'s webrtc_caps comment) -- rtph264pay must
        # stamp that same number on the packets it produces, or the browser
        # will not recognize them as the codec it agreed to receive. Read
        # it directly out of the offer's own SDP text and apply it to the
        # (still fully idle -- no buffer has ever flowed through it yet)
        # payloader before any negotiation state machinery starts, rather
        # than mutating a live element's property mid-negotiation.
        offered_pt = _first_h264_payload_type(sdp_offer_text)
        if offered_pt is not None:

            def _sync_payloader_to_offered_pt() -> None:
                self._payloader.set_property("pt", offered_pt)
                _live_stream_logger.info(
                    "WebRTC state changed: camera %s, offered rtp payload type=%s",
                    self._camera_id,
                    offered_pt,
                )

            await self._run_on_mainloop(_sync_payloader_to_offered_pt)

        def _parse_offer() -> Any:
            ok, sdp_msg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(sdp_offer_text.encode("utf-8"), sdp_msg)
            return GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdp_msg)

        offer_desc = await self._run_on_mainloop(_parse_offer)
        await self._emit_with_promise("set-remote-description", offer_desc)

        answer_reply = await self._emit_with_promise("create-answer", None)
        answer_desc = answer_reply.get_value("answer")
        await self._emit_with_promise("set-local-description", answer_desc)

        await self._wait_for_ice_gathering_complete()

        def _read_local_description() -> str:
            local_desc = self._webrtcbin.get_property("local-description")
            return str(local_desc.sdp.as_text())

        return await self._run_on_mainloop(_read_local_description)

    def _on_ice_gathering_state_changed(self, webrtcbin: Any, _pspec: Any) -> None:
        _Gst, GstWebRTC, _GstSdp = _import_gst()
        state = webrtcbin.get_property("ice-gathering-state")
        _live_stream_logger.info(
            "WebRTC state changed: camera %s, ice-gathering-state=%s", self._camera_id, state
        )
        if state == GstWebRTC.WebRTCICEGatheringState.COMPLETE:
            self._ice_gathering_complete = True

    async def _wait_for_ice_gathering_complete(self, *, timeout_seconds: float = 10.0) -> None:
        elapsed = 0.0
        interval = 0.05
        while not self._ice_gathering_complete:
            await asyncio.sleep(interval)
            elapsed += interval
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"ICE gathering did not complete within {timeout_seconds}s "
                    f"for camera {self._camera_id}"
                )

    async def _run_on_mainloop(self, func: Any) -> Any:
        future = self._bridge.schedule_on_mainloop(func)
        return await asyncio.wrap_future(future)

    async def _emit_with_promise(self, signal_name: str, arg: Any) -> Any:
        Gst, _GstWebRTC, _GstSdp = _import_gst()
        result_future: asyncio.Future[Any] = self._loop.create_future()

        def _on_resolved(promise: Any, _user_data: Any = None) -> None:
            try:
                reply = promise.get_reply()
            except Exception as exc:  # noqa: BLE001 -- propagated to the awaiting caller
                self._loop.call_soon_threadsafe(_set_exception, result_future, exc)
                return
            self._loop.call_soon_threadsafe(_set_result, result_future, reply)

        def _emit() -> None:
            promise = Gst.Promise.new_with_change_func(_on_resolved, None)
            self._webrtcbin.emit(signal_name, arg, promise)

        await self._run_on_mainloop(_emit)
        return await result_future

    # -- Teardown (GLib main-loop thread only) --------------------------

    def teardown(self) -> None:
        Gst, _GstWebRTC, _GstSdp = _import_gst()
        self._appsrc_bridge.remove_appsrc(self._camera_id)

        if self._rtp_probe_id is not None and self._rtp_probe_target is not None:
            self._rtp_probe_target.remove_probe(self._rtp_probe_id)
        self._rtp_probe_id = None
        self._rtp_probe_target = None

        for element in self._elements:
            element.set_state(Gst.State.NULL)
        for element in self._elements:
            self._pipeline.remove(element)
        self._elements = []

        self._appsrc = None
        self._input_selector = None
        self._raw_selector_pad = None
        self._webrtcbin = None

    # -- helpers ----------------------------------------------------------

    def _make(self, Gst: Any, factory_name: str, element_name: str) -> Any:
        element = Gst.ElementFactory.make(factory_name, element_name)
        if element is None:
            raise RuntimeError(f"Failed to create {factory_name!r} ({element_name!r})")
        return element

    def _link(self, upstream: Any, downstream: Any) -> None:
        if not upstream.link(downstream):
            raise RuntimeError(
                f"Failed to link {upstream.get_name()!r} -> {downstream.get_name()!r}"
            )

    def _link_pads(self, src_pad: Any, sink_pad: Any) -> None:
        Gst, _GstWebRTC, _GstSdp = _import_gst()
        if src_pad is None or sink_pad is None:
            raise RuntimeError(f"Missing pad while linking WebRTC branch for {self._camera_id}")
        if src_pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(
                f"Failed to link pads while building WebRTC branch for {self._camera_id}"
            )


_H264_RTPMAP_RE = re.compile(r"^a=rtpmap:(\d+)\s+H264/", re.MULTILINE)


def _first_h264_payload_type(sdp_text: str) -> int | None:
    """The first RTP payload type number the offer's own SDP text assigns
    to H264 (SDP lists codecs in the offerer's preference order) -- ``None``
    if the offer proposes no H264 payload at all."""
    match = _H264_RTPMAP_RE.search(sdp_text)
    return int(match.group(1)) if match else None


def _set_result(future: asyncio.Future[Any], value: Any) -> None:
    if not future.done():
        future.set_result(value)


def _set_exception(future: asyncio.Future[Any], exc: Exception) -> None:
    if not future.done():
        future.set_exception(exc)
