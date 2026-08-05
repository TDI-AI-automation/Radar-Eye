"""Generic WebRTC publish transport (ADR-028): ``rtph264pay -> webrtcbin``,
rebuilt fresh on every browser connection, linked off a persistent
upstream H.264 source. Any subsystem that needs "one already-encoded
H.264 source -> browser" uses this -- Live Streaming (Phase 2) and AI
Streaming (Phase 5) alike, differing only in which subsystem's stream
``upstream`` is (``shared.media_transport.build_source_element()``'s
return value for Live Streaming; AI Runtime's own annotated encode
branch for AI Streaming). Neither subsystem shares a running instance of
anything here -- only this source file (ADR-028's "shared code vs.
shared ownership" distinction).

Promoted from ``apps/deepstream/app/live_stream/branch.py``'s
hardware-proven webrtcbin mechanics -- not moved wholesale: that
module's dual-input ``input-selector``, appsrc bitstream bridging, and
OSD annotated-encode branch are all DeepStream-specific (Stage C AI
on/off switching) and stay there. This file keeps only what is true of
any H.264-over-WebRTC publish regardless of which subsystem's stream it
is: the payloader/caps/webrtcbin triple, the promise-based SDP offer/
answer exchange, and the rebuild-fresh-per-connection discipline below.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    gi.require_version("GstWebRTC", "1.0")
    gi.require_version("GstSdp", "1.0")
    from gi.repository import Gst, GstSdp, GstWebRTC  # noqa: PLC0415

    return Gst, GstWebRTC, GstSdp


_H264_RTPMAP_RE = re.compile(r"^a=rtpmap:(\d+)\s+H264/", re.MULTILINE)


def _first_h264_payload_type(sdp_text: str) -> int | None:
    """The first RTP payload type number the offer's own SDP text assigns
    to H264 (SDP lists codecs in the offerer's preference order) --
    ``None`` if the offer proposes no H264 payload at all."""
    match = _H264_RTPMAP_RE.search(sdp_text)
    return int(match.group(1)) if match else None


class WebRtcBranch:
    """One camera's WebRTC publish point. ``upstream`` must already be
    added to ``pipeline`` and PLAYING (or about to be, via
    ``sync_state_with_parent()``), producing byte-stream H.264 -- either
    an element/bin with a single static/ghost ``"src"`` pad, or a
    ``tee`` (a fresh request pad is auto-requested via ``Element.link()``
    each connection) when the caller needs ``upstream`` to keep flowing
    independent of whether any browser is currently connected. This
    class never owns, builds, or tears down ``upstream`` itself -- only
    links a fresh payloader to it (and, if it's a tee, releases the
    request pad it used) per connection.

    A fresh payloader/capsfilter/webrtcbin triple is built for *every*
    ``handle_offer()`` call, never reused across browser connections --
    hardware-confirmed (building the original DeepStream Live Streaming
    feature this was promoted from): a reused webrtcbin's client-side
    ICE connectivity gets permanently stuck at "checking" on the second
    and every subsequent connection to the same camera, 100%
    reproducible. Rebuilding fresh sidesteps relying on libnice/
    webrtcbin's own ICE-restart support entirely -- every connection is
    structurally identical to the (always-reliable) first one.

    Element construction/teardown must run on the GLib main-loop thread
    (``bridge.schedule_on_mainloop``) -- ``handle_offer()`` is the one
    async entry point, bridging the promise-based GLib SDP/ICE exchange
    to asyncio the same way ``AsyncBridge`` bridges every other GLib
    callback in this codebase.
    """

    def __init__(
        self,
        pipeline: Any,
        upstream: Any,
        camera_id: uuid.UUID,
        *,
        stun_servers: list[str],
        bridge: Any,
        loop: asyncio.AbstractEventLoop,
        on_first_rtp_packet: Callable[[], None] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._upstream = upstream
        self._camera_id = camera_id
        self._stun_servers = stun_servers
        self._bridge = bridge
        self._loop = loop
        self._on_first_rtp_packet = on_first_rtp_packet

        self._elements: list[Any] = []
        """payloader, webrtc_caps, webrtcbin -- rebuilt fresh on every
        handle_offer() call. Deliberately excludes ``upstream``, which
        this class never adds/removes/NULLs."""
        self._upstream_pad: Any = None
        """The specific pad on ``upstream`` this connection's payloader
        linked to -- captured at link time rather than assumed (e.g.
        ``upstream.get_static_pad("src")``) because ``upstream`` may be
        a tee: ``Element.link()`` auto-requests a fresh branch pad each
        call, and only the payloader's own resulting peer reliably
        identifies it. Used to quiesce (teardown) and, if it turns out
        to be a request pad, release it -- the one bit of upstream
        cleanup that is this connection's own, not upstream's owner's."""
        self._payloader: Any = None
        self._webrtc_caps: Any = None
        self._webrtcbin: Any = None
        self._rtp_probe_target: Any = None
        self._rtp_probe_id: int | None = None
        self._first_rtp_packet_seen = False
        self._ice_gathering_complete = False

    # -- Transport construction/teardown (GLib main-loop thread only) ---

    def _build_transport(self) -> None:
        Gst, GstWebRTC, _GstSdp = _import_gst()

        payloader = self._make(Gst, "rtph264pay", f"webrtc-pay-{self._camera_id}")
        payloader.set_property("pt", 96)  # placeholder -- reset to whatever the
        # browser's offer actually negotiates in handle_offer(), before any
        # real data flows.
        payloader.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe
        self._pipeline.add(payloader)
        self._elements.append(payloader)
        self._link(self._upstream, payloader)
        self._upstream_pad = payloader.get_static_pad("sink").get_peer()
        self._payloader = payloader

        # webrtcbin's create-answer runs before any real data has ever
        # flowed through this branch, so it has no caps information on its
        # sink pad yet unless told explicitly -- without this, webrtcbin
        # falls back to its own default codec preference instead of H264
        # and negotiation degrades to "inactive". Deliberately no
        # ``payload=`` field (hardware-confirmed): a browser's offer picks
        # its own dynamic H264 payload type (not necessarily 96), and
        # GStreamer's compatible-transceiver search requires an *exact*
        # match when both sides declare a fixed value -- rtph264pay's own
        # pad template already advertises the full dynamic range
        # (payload=[96,127]), so leaving this field unconstrained lets it
        # intersect with whatever number the browser's offer uses.
        webrtc_caps = self._make(Gst, "capsfilter", f"webrtc-caps-{self._camera_id}")
        webrtc_caps.set_property(
            "caps",
            Gst.Caps.from_string(
                "application/x-rtp,media=video,encoding-name=H264,clock-rate=90000"
            ),
        )
        self._pipeline.add(webrtc_caps)
        self._elements.append(webrtc_caps)
        self._link(payloader, webrtc_caps)
        self._webrtc_caps = webrtc_caps

        self._first_rtp_packet_seen = False
        self._rtp_probe_target = webrtc_caps.get_static_pad("src")
        self._rtp_probe_id = self._rtp_probe_target.add_probe(
            Gst.PadProbeType.BUFFER, self._on_rtp_buffer
        )

        webrtcbin = self._make(Gst, "webrtcbin", f"webrtc-bin-{self._camera_id}")
        webrtcbin.set_property("bundle-policy", "max-bundle")
        for stun_server in self._stun_servers:
            webrtcbin.set_property("stun-server", stun_server)
        self._pipeline.add(webrtcbin)
        self._elements.append(webrtcbin)
        webrtcbin.connect("notify::ice-gathering-state", self._on_ice_gathering_state_changed)
        webrtcbin.connect("notify::ice-connection-state", self._on_webrtc_state_changed)
        webrtcbin.connect("notify::connection-state", self._on_webrtc_state_changed)

        webrtc_sink_pad = webrtcbin.get_request_pad("sink_%u")
        if webrtc_sink_pad is None:
            raise RuntimeError(f"Failed to request webrtcbin sink pad for camera {self._camera_id}")
        self._link_pads(Gst, webrtc_caps.get_static_pad("src"), webrtc_sink_pad)
        transceiver = webrtc_sink_pad.get_property("transceiver")
        if transceiver is not None:
            # Server only ever sends video for this feature -- never
            # receives anything back from the browser.
            transceiver.set_property("direction", GstWebRTC.WebRTCRTPTransceiverDirection.SENDONLY)
        self._webrtcbin = webrtcbin

        for element in self._elements:
            element.sync_state_with_parent()

    def _teardown_transport(self) -> None:
        """A no-op before the first ever connection. Quiesces
        ``upstream``'s own src pad first (same IDLE-probe pattern as
        every other pipeline mutation in this codebase): ``upstream``
        stays PLAYING throughout (this class doesn't own it), actively
        producing buffers, so without this guard one could be mid-push
        into the payloader's sink pad at the exact moment this NULLs
        it."""
        if self._webrtcbin is None:
            return
        Gst, _GstWebRTC, _GstSdp = _import_gst()

        if self._rtp_probe_id is not None and self._rtp_probe_target is not None:
            self._rtp_probe_target.remove_probe(self._rtp_probe_id)
        self._rtp_probe_id = None
        self._rtp_probe_target = None

        upstream_pad = self._upstream_pad
        quiesced = threading.Event()

        def _on_idle(_pad: Any, _info: Any) -> Any:
            quiesced.set()
            return Gst.PadProbeReturn.OK

        probe_id = upstream_pad.add_probe(Gst.PadProbeType.IDLE, _on_idle)
        if not quiesced.wait(timeout=1.0):
            logger.warning(
                "Timed out quiescing camera %s's upstream before rebuilding WebRTC "
                "transport -- proceeding anyway",
                self._camera_id,
            )
        upstream_pad.remove_probe(probe_id)

        # Sink-to-source, same discipline (and the same hardware-confirmed
        # reason) as every other pipeline teardown in this codebase.
        for element in reversed(self._elements):
            element.set_state(Gst.State.NULL)
        for element in self._elements:
            self._pipeline.remove(element)
        self._elements = []

        # If upstream is a tee, this connection's branch pad is a request
        # pad this connection itself requested (via Element.link()'s
        # auto-request) -- release it, the one bit of upstream cleanup
        # that belongs to this connection, not to whoever owns upstream.
        # A no-op for a plain static/ghost pad (e.g. the structural
        # tests' single-consumer upstream) -- ghost pads report no pad
        # template at all, hence the None check.
        template = upstream_pad.get_pad_template()
        if template is not None and template.presence == Gst.PadPresence.REQUEST:
            self._upstream.release_request_pad(upstream_pad)
        self._upstream_pad = None

        self._payloader = None
        self._webrtc_caps = None
        self._webrtcbin = None

    # -- Instrumentation ---------------------------------------------------

    def _on_rtp_buffer(self, _pad: Any, _info: Any) -> Any:
        """Runs on a GStreamer streaming thread (pad probe)."""
        Gst, _GstWebRTC, _GstSdp = _import_gst()
        if not self._first_rtp_packet_seen:
            self._first_rtp_packet_seen = True
            logger.info("WebRTC first RTP packet: camera %s", self._camera_id)
            if self._on_first_rtp_packet is not None:
                self._on_first_rtp_packet()
        return Gst.PadProbeReturn.OK

    def _on_webrtc_state_changed(self, webrtcbin: Any, pspec: Any) -> None:
        state = webrtcbin.get_property(pspec.name)
        logger.info("WebRTC state changed: camera %s, %s=%s", self._camera_id, pspec.name, state)

    def _on_ice_gathering_state_changed(self, webrtcbin: Any, _pspec: Any) -> None:
        _Gst, GstWebRTC, _GstSdp = _import_gst()
        state = webrtcbin.get_property("ice-gathering-state")
        logger.info(
            "WebRTC state changed: camera %s, ice-gathering-state=%s", self._camera_id, state
        )
        if state == GstWebRTC.WebRTCICEGatheringState.COMPLETE:
            self._ice_gathering_complete = True

    # -- Signaling (async) ------------------------------------------------

    async def handle_offer(self, sdp_offer_text: str) -> str:
        """Given a browser's non-trickle SDP offer (ICE already fully
        gathered client-side), returns the complete answer SDP (this
        side's ICE also fully gathered) as plain text. Called once per
        *browser connection*, not once per camera lifetime -- rebuilds
        the transport fresh every time (see class docstring)."""
        Gst, GstWebRTC, GstSdp = _import_gst()

        def _rebuild_transport() -> None:
            self._teardown_transport()
            self._build_transport()

        await self._run_on_mainloop(_rebuild_transport)

        # _ice_gathering_complete is an instance field, not tied to any one
        # webrtcbin object -- still needs resetting here even though the
        # webrtcbin above is now always freshly built.
        self._ice_gathering_complete = False

        # The browser's offer picks its own dynamic RTP payload type number
        # for H264 (see _build_transport's webrtc_caps comment) --
        # rtph264pay must stamp that same number on the packets it
        # produces. Read it directly out of the offer's own SDP text and
        # apply it to the (still fully idle) payloader before any
        # negotiation state machinery starts.
        offered_pt = _first_h264_payload_type(sdp_offer_text)
        if offered_pt is not None:

            def _sync_payloader_to_offered_pt() -> None:
                self._payloader.set_property("pt", offered_pt)

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

    # -- Teardown (GLib main-loop thread only) ----------------------------

    def teardown(self) -> None:
        """Full teardown -- call once when the camera itself goes away
        (not per browser disconnect). Never touches ``upstream``: that
        element/bin belongs to whoever constructed this branch."""
        self._teardown_transport()

    # -- helpers ------------------------------------------------------------

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

    def _link_pads(self, Gst: Any, src_pad: Any, sink_pad: Any) -> None:
        if src_pad is None or sink_pad is None:
            raise RuntimeError(f"Missing pad while linking WebRTC branch for {self._camera_id}")
        if src_pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(
                f"Failed to link pads while building WebRTC branch for {self._camera_id}"
            )


def _set_result(future: asyncio.Future[Any], value: Any) -> None:
    if not future.done():
        future.set_result(value)


def _set_exception(future: asyncio.Future[Any], exc: Exception) -> None:
    if not future.done():
        future.set_exception(exc)
