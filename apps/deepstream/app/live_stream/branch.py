"""CameraWebRtcBranch -- one camera's permanent WebRTC publish pipeline.

Built once when a camera connects, torn down once when it disconnects.
AI-annotated-only (ADR-030): a single input chain, taps the AI
pipeline's SGIE tee, no raw passthrough and no runtime source switch.
See ``apps/deepstream/app/live_stream/__init__.py``'s module docstring
for the full branch diagram and the architectural reasoning.

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
import threading
import uuid
from typing import Any

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import LiveStreamSettings, VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.stage_logging import get_stage_logger
from apps.deepstream.app.visualization.osd_renderer import DeepStreamOverlayRenderer
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

logger = logging.getLogger(__name__)
_live_stream_logger = get_stage_logger("live_stream")


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
    gi.require_version("GstWebRTC", "1.0")
    gi.require_version("GstSdp", "1.0")
    from gi.repository import Gst, GstSdp, GstVideo, GstWebRTC  # noqa: PLC0415

    return Gst, GstWebRTC, GstSdp, GstVideo


class CameraWebRtcBranch:
    def __init__(
        self,
        pipeline: Any,
        sgie_tee: Any,
        camera_id: uuid.UUID,
        camera_name: str,
        *,
        streammux_width: int,
        streammux_height: int,
        live_settings: LiveStreamSettings,
        visualization_settings: VisualizationSettings,
        track_annotations: TrackAnnotationRegistry,
        instrumentation: PerformanceInstrumentation | None,
        bridge: AsyncBridge,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._pipeline = pipeline
        self._sgie_tee = sgie_tee
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._width = streammux_width
        self._height = streammux_height
        self._settings = live_settings
        self._visualization_settings = visualization_settings
        self._track_annotations = track_annotations
        self._instrumentation = instrumentation
        self._bridge = bridge
        self._loop = loop

        self._elements: list[Any] = []
        """Persistent, camera-lifetime elements only (the AI-annotated
        input chain) -- built once in build(), torn down once in
        teardown(). Deliberately excludes payloader/webrtc_caps/webrtcbin;
        see ``_transport_elements``."""
        self._chain_output: Any = None
        """The annotated input chain's tail element (``h264parse``) --
        what the transport's payloader links off."""

        self._transport_elements: list[Any] = []
        """payloader, webrtc_caps, webrtcbin -- rebuilt fresh on *every*
        handle_offer() call, not just the first. See that method's own
        docstring: a persistent, reused webrtcbin was found (hardware-
        confirmed) to never properly restart ICE on a second browser
        connection -- client-side ICE connectivity permanently stuck at
        "checking", 100% reproducible from the second connection onward.
        Rebuilding fresh sidesteps relying on libnice/webrtcbin's own
        ICE-restart support entirely: every connection is structurally
        identical to the (always-reliable) first one."""
        self._payloader: Any = None
        self._webrtc_caps: Any = None
        self._webrtcbin: Any = None
        self._rtp_probe_target: Any = None
        self._rtp_probe_id: int | None = None
        self._first_rtp_packet_seen = False
        self._ice_gathering_complete = False

        self._sgie_tee_pad: Any = None
        self._annotated_encoder: Any = None
        self._renderer: DeepStreamOverlayRenderer | None = None
        self._annotate_probe_target: Any = None
        self._annotate_probe_id: int | None = None

    # -- Construction (GLib main-loop thread only) ---------------------

    def build(self) -> None:
        """Constructs and links the persistent, camera-lifetime part of the
        branch: the AI-annotated input chain. Deliberately does *not*
        construct payloader/webrtc_caps/webrtcbin -- see
        ``_build_webrtc_transport``, built fresh on every ``handle_offer()``
        call instead. Raises immediately on any construction/link failure,
        matching VisualizationPipelineBuilder's own "fail fast, never
        return a half-built branch" discipline."""
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

        self._chain_output = self._annotated_input_chain(Gst)

        for element in self._elements:
            element.sync_state_with_parent()

    def _build_webrtc_transport(self) -> None:
        """Builds a fresh payloader -> webrtc_caps -> webrtcbin chain and
        links it off the (persistent, already-PLAYING) annotated input
        chain. Called from ``handle_offer()`` for *every* browser
        connection -- see that method's docstring for why a reused
        webrtcbin doesn't work. GLib main-loop thread only."""
        Gst, GstWebRTC, _GstSdp, _GstVideo = _import_gst()
        assert self._chain_output is not None

        payloader = self._make(Gst, "rtph264pay", f"live-pay-{self._camera_id}")
        payloader.set_property("pt", 96)  # placeholder -- reset to whatever
        # the browser's offer actually negotiates, in handle_offer() below,
        # before any real data flows. 96 is never itself sent over the wire.
        payloader.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe
        self._pipeline.add(payloader)
        self._transport_elements.append(payloader)
        self._link(self._chain_output, payloader)
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
        self._transport_elements.append(webrtc_caps)
        self._link(payloader, webrtc_caps)
        self._webrtc_caps = webrtc_caps

        self._first_rtp_packet_seen = False
        self._rtp_probe_target = webrtc_caps.get_static_pad("src")
        self._rtp_probe_id = self._rtp_probe_target.add_probe(
            Gst.PadProbeType.BUFFER, self._on_rtp_buffer
        )

        webrtcbin = self._make(Gst, "webrtcbin", f"live-webrtc-{self._camera_id}")
        webrtcbin.set_property("bundle-policy", "max-bundle")
        for stun_server in self._settings.stun_servers:
            webrtcbin.set_property("stun-server", stun_server)
        self._pipeline.add(webrtcbin)
        self._transport_elements.append(webrtcbin)
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
            transceiver.set_property("direction", GstWebRTC.WebRTCRTPTransceiverDirection.SENDONLY)
        self._webrtcbin = webrtcbin

        for element in self._transport_elements:
            element.sync_state_with_parent()

    def _teardown_webrtc_transport(self) -> None:
        """Tears down the current payloader/webrtc_caps/webrtcbin (if any
        -- a no-op before the first ever connection). GLib main-loop
        thread only.

        Quiesces the selector's src pad first, exactly like
        ``DeepStreamPipeline.remove_source()``'s own IDLE-probe pattern
        (see that method's docstring for the hardware-confirmed reason):
        the selector is persistent and stays PLAYING throughout, actively
        fed by the still-live raw/annotated chains, so without this guard
        a buffer could be mid-push into the payloader's sink pad at the
        exact moment this method NULLs it -- the same class of freeze this
        whole subsystem has already been hardware-confirmed to hit once."""
        if self._webrtcbin is None:
            return
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

        if self._rtp_probe_id is not None and self._rtp_probe_target is not None:
            self._rtp_probe_target.remove_probe(self._rtp_probe_id)
        self._rtp_probe_id = None
        self._rtp_probe_target = None

        chain_output_pad = self._chain_output.get_static_pad("src")
        quiesced = threading.Event()

        def _on_idle(_pad: Any, _info: Any) -> Any:
            quiesced.set()
            return Gst.PadProbeReturn.OK

        probe_id = chain_output_pad.add_probe(Gst.PadProbeType.IDLE, _on_idle)
        if not quiesced.wait(timeout=1.0):
            logger.warning(
                "Timed out quiescing camera %s's annotated chain before rebuilding "
                "WebRTC transport -- proceeding anyway",
                self._camera_id,
            )
        chain_output_pad.remove_probe(probe_id)

        # Sink-to-source, same discipline (and the same hardware-confirmed
        # reason) as teardown()'s own reversed-NULL loop below.
        for element in reversed(self._transport_elements):
            element.set_state(Gst.State.NULL)
        for element in self._transport_elements:
            self._pipeline.remove(element)
        self._transport_elements = []

        self._payloader = None
        self._webrtc_caps = None
        self._webrtcbin = None

    def _annotated_input_chain(self, Gst: Any) -> Any:
        """tee -> queue -> nvvideoconvert(RGBA) -> [overlay probe, reusing
        the existing Visualization overlay renderer] -> nvdsosd ->
        nvvideoconvert(NV12) -> nvv4l2h264enc -> h264parse. Mirrors
        visualization/pipeline_builder.py's exact branch shape, including
        the hardware-confirmed disable-passthrough requirement (see that
        module's own comment for the corruption bug this avoids) --
        independent of whether Visualization's own RTSP output is
        enabled. This is the AI pipeline's own already-produced output
        (SGIE tee is upstream, untouched); this method only taps it and
        encodes what's already there -- it does not re-run or redesign
        any part of PGIE/NvDCF/SGIE."""
        queue = self._make(Gst, "queue", f"live-osd-queue-{self._camera_id}")
        queue.set_property("leaky", 2)
        queue.set_property("max-size-buffers", 4)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)

        convert_in = self._make(Gst, "nvvideoconvert", f"live-osd-convert-in-{self._camera_id}")
        convert_in.set_property("nvbuf-memory-type", 2)
        convert_in.set_property("disable-passthrough", True)
        caps_rgba = self._make(Gst, "capsfilter", f"live-osd-caps-rgba-{self._camera_id}")
        caps_rgba.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM),format=RGBA"))

        osd = self._make(Gst, "nvdsosd", f"live-osd-{self._camera_id}")

        convert_out = self._make(Gst, "nvvideoconvert", f"live-osd-convert-out-{self._camera_id}")
        convert_out.set_property("nvbuf-memory-type", 2)
        convert_out.set_property("disable-passthrough", True)
        caps_nv12 = self._make(Gst, "capsfilter", f"live-osd-caps-nv12-{self._camera_id}")
        caps_nv12.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw(memory:NVMM),format=NV12,width={self._width},height={self._height}"
            ),
        )

        encoder = self._make(Gst, "nvv4l2h264enc", f"live-annotated-encoder-{self._camera_id}")
        encoder.set_property("bitrate", self._settings.output_bitrate)
        # iframeinterval: default is large enough that a WebRTC viewer
        # connecting mid-stream can wait a long time for its first real
        # keyframe, decoding only P-frames against a reference it never
        # received -- the classic "solid black/green until the first IDR
        # arrives" artifact (same root cause already diagnosed and fixed
        # for the visualization pipeline's encoder, RM-11.SIV Phase 5 --
        # see apps/deepstream/app/visualization/pipeline_builder.py --
        # never applied here). One keyframe per second matches this
        # payloader's own config-interval=-1 (in-band SPS/PPS every
        # keyframe, set below).
        encoder.set_property("iframeinterval", self._visualization_settings.output_fps)
        # Match the camera's own real profile (Main; hardware-confirmed,
        # see docs/DEEPSTREAM_PIPELINE_SPEC.md's tee-placement
        # investigation) rather than nvv4l2h264enc's default
        # (Constrained-Baseline). Hardware-verified: leaving this at the
        # default means every A<->B switch also changes the negotiated
        # H.264 *profile* mid-stream, not just the picture content -- a
        # decoder-reinitialization cost most browser H.264 decoders
        # handle poorly (observed: a second switch cycle's browser-side
        # decode gap growing to over 10s, far past the transport-level
        # "first packet"/"keyframe received" latency this branch itself
        # measures). Matching profiles removes that reinitialization
        # entirely -- the decoder sees the same profile throughout, only
        # a new SPS/PPS and picture content at each switch.
        encoder.set_property("profile", 2)  # GST_V4L2_H264_VIDENC_MAIN_PROFILE
        parser = self._make(Gst, "h264parse", f"live-annotated-parse-{self._camera_id}")

        for element in (queue, convert_in, caps_rgba, osd, convert_out, caps_nv12, encoder, parser):
            self._pipeline.add(element)
            self._elements.append(element)
        self._link(queue, convert_in)
        self._link(convert_in, caps_rgba)
        self._link(caps_rgba, osd)
        self._link(osd, convert_out)
        self._link(convert_out, caps_nv12)
        self._link(caps_nv12, encoder)
        self._link(encoder, parser)
        self._annotated_encoder = encoder

        tee_pad = self._sgie_tee.get_request_pad("src_%u")
        if tee_pad is None:
            raise RuntimeError(f"Failed to request SGIE tee pad for camera {self._camera_id}")
        self._sgie_tee_pad = tee_pad
        self._link_pads(tee_pad, queue.get_static_pad("sink"))

        self._renderer = DeepStreamOverlayRenderer(
            self._visualization_settings,
            camera_id=self._camera_id,
            camera_name=self._camera_name,
            track_annotations=self._track_annotations,
            instrumentation=self._instrumentation,
        )
        self._annotate_probe_target = convert_in.get_static_pad("src")
        self._annotate_probe_id = self._annotate_probe_target.add_probe(
            Gst.PadProbeType.BUFFER, self._renderer.probe_callback
        )
        return parser

    # -- Transport-level logging -----------------------------------------

    def _on_rtp_buffer(self, _pad: Any, _info: Any) -> Any:
        """Runs on a GStreamer streaming thread (pad probe)."""
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()
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
        server's ICE also fully gathered) as plain text.

        Called once per *browser connection*, not once per camera lifetime
        -- the operator's browser gets a brand new ``RTCPeerConnection``
        (and therefore a brand new offer) every time Live Monitoring
        mounts (page navigation, refresh, reconnect), which happens
        routinely and repeatedly against the same long-lived branch.

        Rebuilds payloader/webrtc_caps/webrtcbin fresh on every call (see
        ``_build_webrtc_transport``'s own docstring) -- hardware-confirmed
        real bug, found investigating this exact symptom: a *reused*
        webrtcbin's client-side ICE connectivity got permanently stuck at
        "checking" on the second and every subsequent connection (100%
        reproducible), even after fixing the separate, also-real
        ``_ice_gathering_complete`` staleness bug below. Rebuilding fresh
        sidesteps relying on libnice/webrtcbin's own ICE-restart support
        -- every connection is now structurally identical to the (always
        reliable) first one. Never touches the persistent annotated input
        chain."""
        if self._chain_output is None:
            raise RuntimeError(f"WebRTC branch not built for camera {self._camera_id}")
        Gst, GstWebRTC, GstSdp, _GstVideo = _import_gst()

        def _rebuild_transport() -> None:
            self._teardown_webrtc_transport()
            self._build_webrtc_transport()

        await self._run_on_mainloop(_rebuild_transport)

        # _ice_gathering_complete is an instance field, not tied to any one
        # webrtcbin object -- still needs resetting here even though the
        # webrtcbin above is now always freshly built, since a fresh
        # object doesn't reset a stale Python-level flag by itself.
        self._ice_gathering_complete = False

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
        _Gst, GstWebRTC, _GstSdp, _GstVideo = _import_gst()
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
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()
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
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

        # Handles the RTP-buffer probe + payloader/webrtc_caps/webrtcbin
        # (including quiescing the annotated chain's src pad first) -- a
        # no-op if no browser ever connected to this camera.
        self._teardown_webrtc_transport()

        if self._annotate_probe_id is not None and self._annotate_probe_target is not None:
            self._annotate_probe_target.remove_probe(self._annotate_probe_id)
        self._annotate_probe_id = None
        self._annotate_probe_target = None
        self._renderer = None

        # Sink-to-source, the reverse of construction order: NULLing an
        # upstream element (e.g. the queue right after the SGIE tee) while
        # its downstream neighbors are still PLAYING can deadlock a
        # streaming thread mid-push -- hardware-confirmed during repeated
        # delete/re-register cycles (real hardware bug: the GLib main-loop
        # thread wedged inside this exact loop, freezing every subsequent
        # pipeline mutation, including unrelated cameras, since it is the
        # only thread that services AsyncBridge.schedule_on_mainloop()).
        # GStreamer's own application manual documents this ordering
        # requirement when removing elements from a running pipeline.
        for element in reversed(self._elements):
            element.set_state(Gst.State.NULL)
        for element in self._elements:
            self._pipeline.remove(element)
        self._elements = []

        if self._sgie_tee_pad is not None:
            self._sgie_tee.release_request_pad(self._sgie_tee_pad)
            self._sgie_tee_pad = None

        self._chain_output = None
        self._annotated_encoder = None
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
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()
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
