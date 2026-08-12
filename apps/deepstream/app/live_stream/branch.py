"""CameraWebRtcBranch -- one camera's permanent WebRTC publish pipeline.

Built once when a camera connects, torn down once when it disconnects.
AI-annotated-only (ADR-030): a single input chain, taps the AI
pipeline's SGIE tee, no raw passthrough and no runtime source switch.
See ``apps/deepstream/app/live_stream/__init__.py``'s module docstring
for the full branch diagram and the architectural reasoning.

Element construction/linking must run on the GLib main-loop thread
(``AsyncBridge.schedule_on_mainloop``). ``build()`` is synchronous and is
only ever called already scheduled there by ``manager.py``. ``teardown()``
and ``handle_offer()`` are both ``async``, each internally marshaling its
own pipeline-mutating steps onto the main loop via ``_run_on_mainloop``
(the same bridge ``AsyncBridge`` uses for every other GLib callback in
this codebase) rather than assuming they're already running there --
this lets both await a safe, non-blocking wait for a pad to quiesce
(see ``_teardown_webrtc_transport``) without ever blocking the main loop
thread itself.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
        input chain, the permanent output tee, and its permanent drain
        branch) -- built once in build(), torn down once in teardown().
        Deliberately excludes payloader/webrtc_caps/webrtcbin; see
        ``_transport_elements``."""
        self._output_tee: Any = None
        """Permanent tee immediately downstream of the annotated chain's
        ``h264parse``. Exists so that chain always has a live peer, even
        when no browser is connected -- see build()'s own docstring for
        why an unlinked src pad is not safe here. One branch (built here,
        never released) permanently drains to a fakesink; the transport
        branch below requests/releases its own tee pad per browser
        connection."""
        self._transport_tee_pad: Any = None
        """The output tee's request pad currently feeding the payloader --
        requested in ``_build_webrtc_transport``, released in
        ``_teardown_webrtc_transport``. ``None`` when no browser is
        connected."""
        self._reconfigure_probe_id: int | None = None
        """Upstream-event probe on ``_transport_tee_pad`` that drops
        ``GST_EVENT_RECONFIGURE`` -- see ``_build_webrtc_transport``'s own
        docstring for why. Installed alongside the pad, removed in
        ``_teardown_webrtc_transport`` before the pad is released."""
        self._activation_block_probe_id: int | None = None
        """Downstream-data probe on ``_transport_tee_pad`` that holds any
        premature push until the freshly-built transport branch has
        actually reached PLAYING -- see ``_wait_for_transport_activation``'s
        own docstring for the hardware-confirmed race this closes.
        Installed in ``_build_webrtc_transport``, removed by
        ``_wait_for_transport_activation`` once activation is confirmed
        (or on timeout, so a failed activation never leaves the pad
        blocked worse than before)."""

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

        self._rebuild_lock = asyncio.Lock()
        """Serializes handle_offer()'s teardown+build+negotiate sequence
        end to end. Without this, two browser connections arriving close
        together (hardware-confirmed real trigger: React StrictMode's
        double-mount sends two real offers per page load; also any rapid
        manual reconnect) can each schedule their own rebuild onto the
        GLib main loop -- the *pipeline mutations* themselves still run
        one at a time (schedule_on_mainloop is one thread), but nothing
        previously stopped a second rebuild's teardown from starting
        before the first's negotiation had fully settled the pad it was
        touching. Held for the whole method, not just the pipeline-
        mutation steps, so a second reconnect simply waits its turn
        rather than racing the first."""

    # -- Construction (GLib main-loop thread only) ---------------------

    def build(self) -> None:
        """Constructs and links the persistent, camera-lifetime part of the
        branch: the AI-annotated input chain, followed by a permanent
        output tee with an always-linked drain branch. Deliberately does
        *not* construct payloader/webrtc_caps/webrtcbin -- see
        ``_build_webrtc_transport``, built fresh on every ``handle_offer()``
        call instead. Raises immediately on any construction/link failure,
        matching VisualizationPipelineBuilder's own "fail fast, never
        return a half-built branch" discipline.

        The tee and its drain exist because the annotated chain starts
        receiving real buffers the moment the camera is added -- long
        before any browser necessarily connects. A src pad with no peer
        at all gets NOT_LINKED on every push (unlike an input-selector's
        *inactive* input, which is discarded internally without ever
        attempting a push); once that happens repeatedly the streaming
        thread stops delivering buffers, and linking a real consumer
        later does not wake it back up -- hardware-confirmed for this
        exact failure class in the (now-removed) apps/live_stream
        service's own tee. The drain (small leaky queue -> fakesink,
        ``sync=False`` so it never throttles to the pipeline clock)
        gives the chain a permanent, always-linked peer; the transport
        branch below requests/releases its own, independent tee pad per
        browser connection, so attaching/detaching a browser never
        touches the drain. The transport branch gets its own leaky queue
        too, immediately after the tee, for a related but distinct
        reason -- see ``_build_webrtc_transport``'s own docstring."""
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

        parser = self._annotated_input_chain(Gst)

        tee = self._make(Gst, "tee", f"live-output-tee-{self._camera_id}")
        self._pipeline.add(tee)
        self._elements.append(tee)
        self._link(parser, tee)
        self._output_tee = tee

        drain_queue = self._make(Gst, "queue", f"live-drain-queue-{self._camera_id}")
        drain_queue.set_property("leaky", 2)
        drain_queue.set_property("max-size-buffers", 2)
        drain_queue.set_property("max-size-bytes", 0)
        drain_queue.set_property("max-size-time", 0)
        drain_sink = self._make(Gst, "fakesink", f"live-drain-sink-{self._camera_id}")
        drain_sink.set_property("sync", False)
        drain_sink.set_property("async", False)
        for element in (drain_queue, drain_sink):
            self._pipeline.add(element)
            self._elements.append(element)
        self._link(drain_queue, drain_sink)

        drain_tee_pad = tee.get_request_pad("src_%u")
        if drain_tee_pad is None:
            raise RuntimeError(f"Failed to request drain tee pad for camera {self._camera_id}")
        self._link_pads(drain_tee_pad, drain_queue.get_static_pad("sink"))

        for element in self._elements:
            element.sync_state_with_parent()

    def _build_webrtc_transport(self) -> None:
        """Builds a fresh queue -> payloader -> webrtc_caps -> webrtcbin
        chain and links it off a freshly-requested pad on the (persistent,
        already-PLAYING) output tee -- never off the annotated chain
        directly, so the chain's own downstream peer (the tee) is never
        disturbed by a browser connecting/disconnecting. Called from
        ``handle_offer()`` for *every* browser connection -- see that
        method's docstring for why a reused webrtcbin doesn't work.
        GLib main-loop thread only.

        The leaky queue immediately after the tee is not optional --
        hardware-confirmed, real deadlock: without it, this branch linked
        the tee's request pad directly to ``rtph264pay``, and a `tee`'s
        push to every branch happens synchronously on whatever thread is
        driving it. When ``webrtcbin``'s own internal send path stopped
        draining (confirmed via ``gdb`` thread backtraces: its internal
        queue and DTLS threads blocked on a dead/unresponsive peer -- the
        exact state a reconnect leaves an old, not-yet-torn-down browser
        connection in), that backpressure propagated synchronously back
        through ``rtph264pay`` -> the tee's own push call -> the *shared*
        ``sgie_tee`` this tee forks off of -> froze PGIE/tracker/SGIE for
        every camera, not just this branch's WebRTC delivery. This is the
        same "queue after every tee branch" idiom already used for this
        branch's own drain (build()'s own docstring) and for
        Visualization's ``viz-queue`` -- this branch was simply missing it
        on its transport side. Sized to match the drain: small, leaky, so
        it absorbs exactly this kind of backpressure by dropping frames
        rather than ever blocking upstream.

        The upstream-``RECONFIGURE``-drop probe on the freshly-requested
        tee pad, installed immediately below, is a second and separate
        isolation fix -- hardware-confirmed via ``GST_DEBUG=v4l2:6,
        v4l2h264enc:6,v4l2videoenc:6`` tracing, precisely correlated to
        wall-clock logs: linking a *new* branch onto ``output_tee`` marks
        that pad as needing reconfiguration, and the tee forwards the
        resulting ``GST_EVENT_RECONFIGURE`` upstream through its sink pad
        on the very next push -- straight into the shared, persistent
        ``nvv4l2h264enc`` (this is documented, intended GStreamer
        behaviour, not a bug in ``tee``: see gst-docs'
        ``additional/design/negotiation.md``, "the purpose of the
        reconfigure event is to travel upstream and make elements
        renegotiate their caps or reconfigure their buffer pools"). The
        encoder answers by fully renegotiating and restarting its
        internal V4L2 output thread (``gst_v4l2_video_enc_negotiate``,
        "Leaving output thread" in its own trace) even though its actual
        output format never changes connection to connection -- fixed
        NV12->H264, fixed profile/bitrate/resolution; only the RTP
        payload-type number differs, and that's set via a plain property
        on ``rtph264pay`` below, entirely downstream of the encoder, no
        renegotiation needed for it. Under sustained rapid reconnects, one
        of these renegotiation-triggered restarts hung permanently inside
        the new output thread's first buffer-allocation call --
        confirmed, this hardware, this trace -- silently starving
        ``h264parse``'s src pad and therefore *both* tee branches
        (including the drain), while PGIE/tracker/SGIE kept running
        unaffected the entire time (they sit upstream of this tee
        entirely). The permanent drain branch already proves this tee can
        run indefinitely with an attached branch that never triggers
        encoder reconfiguration; dropping ``RECONFIGURE`` here makes the
        transport branch behave the same way instead of asking the
        encoder to renegotiate on every single reconnect. Every other
        upstream event type (QOS, LATENCY, ...) passes through untouched
        -- only this one event, and only on this one pad, is affected.
        Does not touch webrtcbin's own SDP/ICE negotiation (a separate,
        higher-level, promise/signal-based mechanism, not GStreamer
        pad-level caps renegotiation) and does not affect ALLOCATION
        queries (a different query type, not an event, unaffected by an
        ``EVENT_UPSTREAM`` probe)."""
        Gst, GstWebRTC, _GstSdp, _GstVideo = _import_gst()
        assert self._output_tee is not None

        transport_tee_pad = self._output_tee.get_request_pad("src_%u")
        if transport_tee_pad is None:
            raise RuntimeError(f"Failed to request transport tee pad for camera {self._camera_id}")
        self._transport_tee_pad = transport_tee_pad

        # Installed before anything downstream is even constructed, let
        # alone linked -- closes the activation race at its earliest
        # possible point. See _wait_for_transport_activation's docstring
        # for the hardware-confirmed mechanism this defends against and
        # why polling get_state() is used to release it rather than a
        # fixed delay.
        def _hold_until_active(_pad: Any, _info: Any) -> Any:
            return Gst.PadProbeReturn.OK

        self._activation_block_probe_id = transport_tee_pad.add_probe(
            Gst.PadProbeType.BLOCK_DOWNSTREAM, _hold_until_active
        )

        def _drop_reconfigure(_pad: Any, info: Any) -> Any:
            event = info.get_event()
            if event is not None and event.type == Gst.EventType.RECONFIGURE:
                return Gst.PadProbeReturn.DROP
            return Gst.PadProbeReturn.OK

        self._reconfigure_probe_id = transport_tee_pad.add_probe(
            Gst.PadProbeType.EVENT_UPSTREAM, _drop_reconfigure
        )

        transport_queue = self._make(Gst, "queue", f"live-transport-queue-{self._camera_id}")
        transport_queue.set_property("leaky", 2)
        transport_queue.set_property("max-size-buffers", 5)
        transport_queue.set_property("max-size-bytes", 0)
        transport_queue.set_property("max-size-time", 0)
        self._pipeline.add(transport_queue)
        self._transport_elements.append(transport_queue)
        self._link_pads(transport_tee_pad, transport_queue.get_static_pad("sink"))

        payloader = self._make(Gst, "rtph264pay", f"live-pay-{self._camera_id}")
        payloader.set_property("pt", 96)  # placeholder -- reset to whatever
        # the browser's offer actually negotiates, in handle_offer() below,
        # before any real data flows. 96 is never itself sent over the wire.
        payloader.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe
        self._pipeline.add(payloader)
        self._transport_elements.append(payloader)
        self._link(transport_queue, payloader)
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

    async def _teardown_webrtc_transport(self) -> None:
        """Tears down the current payloader/webrtc_caps/webrtcbin (if any
        -- a no-op before the first ever connection).

        Blocks the transport's own tee branch pad first -- ``BLOCK_DOWNSTREAM``,
        not ``IDLE``. This distinction is load-bearing, found the hard way
        (real hardware, repeated rapid reconnects): an ``IDLE`` probe only
        fires if the pad happens to already be between buffers at the
        exact moment it's checked, which is not guaranteed on a live,
        continuously-fed tee branch -- a real reconnect burst hit that gap,
        the wait timed out, and the old "proceed anyway" fallback NULLed
        elements out from under a buffer that actually was still mid-push,
        wedging the GLib main-loop thread and freezing the *entire* shared
        pipeline (every camera, not just this branch) until the process
        was restarted. ``BLOCK_DOWNSTREAM`` has no such gap: it is
        guaranteed to fire, either immediately (pad already idle) or on
        the very next buffer attempt.

        The wait itself is bridged to asyncio (``loop.call_soon_threadsafe``,
        the exact same pattern ``_emit_with_promise`` already uses for
        GLib promise callbacks) rather than blocking the GLib main-loop
        thread on a ``threading.Event`` -- also found the hard way: under
        real back-to-back-reconnect stress, blocking the main-loop thread
        itself while waiting for this pad's own callback measurably
        starved the probe's ability to fire at all, since every other
        pending ``schedule_on_mainloop`` callable (including, transitively,
        whatever the probe's own dispatch needed) was stuck behind that
        same blocked thread -- a self-inflicted stall, not a GStreamer
        one. Suspending the *coroutine* instead of the *thread* leaves the
        main loop free to keep servicing everything else while this
        specific wait is pending.

        If it still doesn't fire within the generous safety-net timeout,
        the only safe response is to leave the existing transport exactly
        as it is (undo the block attempt, raise, touch nothing else)
        rather than risk the same class of freeze this replaces -- see
        ``handle_offer()``'s own ``_rebuild_lock``, which prevents the
        overlapping-reconnect scenario that originally triggered this.
        Only the transport branch's own requested tee pad is ever touched
        -- the tee's permanent drain branch (build()'s own doc) is
        untouched, so the annotated chain always keeps a live peer even
        while no browser is connected."""

        def _has_webrtcbin() -> bool:
            return self._webrtcbin is not None

        if not await self._run_on_mainloop(_has_webrtcbin):
            return
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

        def _remove_rtp_probe() -> None:
            if self._rtp_probe_id is not None and self._rtp_probe_target is not None:
                self._rtp_probe_target.remove_probe(self._rtp_probe_id)
            self._rtp_probe_id = None
            self._rtp_probe_target = None

        await self._run_on_mainloop(_remove_rtp_probe)

        blocked: asyncio.Future[None] = self._loop.create_future()

        def _on_blocked(_pad: Any, _info: Any) -> Any:
            self._loop.call_soon_threadsafe(_set_result, blocked, None)
            return Gst.PadProbeReturn.OK

        def _install_probe() -> tuple[Any, int]:
            pad = self._transport_tee_pad
            probe_id = pad.add_probe(Gst.PadProbeType.BLOCK_DOWNSTREAM, _on_blocked)
            return pad, probe_id

        transport_tee_pad, probe_id = await self._run_on_mainloop(_install_probe)

        try:
            await asyncio.wait_for(asyncio.shield(blocked), timeout=5.0)
        except asyncio.TimeoutError:
            # See this method's own docstring: undo the block attempt
            # completely (remove the never-fired probe) rather than leave
            # it dangling -- a dangling probe still blocks the pad the
            # moment it does eventually fire, with nothing left to ever
            # release it (hardware-confirmed: this exact mistake was made
            # and reproduced once already, turning one slow attempt into
            # every subsequent reconnect failing forever).
            def _undo_probe() -> None:
                transport_tee_pad.remove_probe(probe_id)

            await self._run_on_mainloop(_undo_probe)
            logger.error(
                "Camera %s: transport tee pad did not block within 5s -- "
                "refusing to tear down a possibly-live branch; this reconnect "
                "attempt fails, the block attempt is undone, the branch is "
                "left exactly as it was",
                self._camera_id,
            )
            raise RuntimeError(
                f"Camera {self._camera_id}: transport tee pad never blocked; "
                "aborting teardown to avoid an unsafe live unlink"
            ) from None

        def _finish_teardown() -> None:
            transport_tee_pad.remove_probe(probe_id)
            if self._reconfigure_probe_id is not None:
                transport_tee_pad.remove_probe(self._reconfigure_probe_id)
                self._reconfigure_probe_id = None

            # Sink-to-source, same discipline (and the same hardware-
            # confirmed reason) as teardown()'s own reversed-NULL loop.
            # Safe now: the block probe above guarantees no buffer can be
            # mid-push past transport_tee_pad.
            for element in reversed(self._transport_elements):
                element.set_state(Gst.State.NULL)
            for element in self._transport_elements:
                self._pipeline.remove(element)
            self._transport_elements = []

            self._output_tee.release_request_pad(transport_tee_pad)
            self._transport_tee_pad = None

            self._payloader = None
            self._webrtc_caps = None
            self._webrtcbin = None

        await self._run_on_mainloop(_finish_teardown)

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
        chain or the output tee's permanent drain branch.

        The whole method runs under ``self._rebuild_lock`` -- see that
        field's own docstring. A second, overlapping call (e.g. React
        StrictMode's double-mount, or a fast manual reconnect) simply
        waits for the first to finish end to end rather than racing it;
        this is what actually closes the deadlock ``_teardown_webrtc_transport``'s
        ``BLOCK_DOWNSTREAM`` probe defends against, not just a fallback
        for it."""
        if self._output_tee is None:
            raise RuntimeError(f"WebRTC branch not built for camera {self._camera_id}")
        Gst, GstWebRTC, GstSdp, _GstVideo = _import_gst()

        async with self._rebuild_lock:
            await self._teardown_webrtc_transport()
            await self._run_on_mainloop(self._build_webrtc_transport)
            await self._wait_for_transport_activation()

            # _ice_gathering_complete is an instance field, not tied to any
            # one webrtcbin object -- still needs resetting here even
            # though the webrtcbin above is now always freshly built,
            # since a fresh object doesn't reset a stale Python-level flag
            # by itself.
            self._ice_gathering_complete = False

            # The browser's offer picks its own dynamic RTP payload type
            # number for H264 (see build()'s webrtc_caps comment) --
            # rtph264pay must stamp that same number on the packets it
            # produces, or the browser will not recognize them as the
            # codec it agreed to receive. Read it directly out of the
            # offer's own SDP text and apply it to the (still fully idle
            # -- no buffer has ever flowed through it yet) payloader
            # before any negotiation state machinery starts, rather than
            # mutating a live element's property mid-negotiation.
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
                return GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.OFFER, sdp_msg
                )

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

    async def _wait_for_transport_activation(self, *, timeout_seconds: float = 5.0) -> None:
        """Polls every freshly-built transport element's *actual* state
        (``get_state(0)`` -- an immediate, non-blocking read of what the
        element has really reached, not what was merely requested) until
        all report PLAYING, then releases the activation-block probe
        ``_build_webrtc_transport`` installed on the tee's request pad
        before linking anything to it. Always releases the probe, even
        on timeout/failure (`finally`) -- a failed activation must never
        leave the pad blocked *worse* than the race it's meant to
        prevent.

        Bridges the wait through ``asyncio.sleep`` -- the same pattern
        ``_wait_for_ice_gathering_complete`` already uses for a sibling
        async-GStreamer-state problem -- rather than a blocking
        ``element.get_state(timeout)`` call on the GLib main-loop
        thread. That distinction is load-bearing: ``webrtcbin``'s own
        internal setup (ICE agent, DTLS context) is itself driven by
        GSources on that same main context, so synchronously blocking
        the thread waiting for it to finish transitioning risks the
        exact self-inflicted stall ``_teardown_webrtc_transport``'s own
        docstring documents for a different wait on this same main loop.

        Why this exists -- hardware-confirmed, real race, proven via
        ``GST_DEBUG=tee:6,queue:5,webrtcbin:5`` tracing precisely
        correlated to wall-clock logs: without the activation-block
        probe held here, the tee's own driving thread (continuous, at
        the encoder's framerate) can push the very first buffer into a
        freshly-linked transport pad *before* ``sync_state_with_parent()``'s
        requested transitions have actually completed -- captured once
        with ``webrtcbin`` still fully in ``NULL`` state 46
        *microseconds* before its own state-change log line fires. A pad
        belonging to a ``NULL``-state element is inherently inactive;
        the push correctly, expectedly returns ``GST_FLOW_FLUSHING``.
        The critical, previously-unproven fact this investigation
        established: ``tee`` does not retry a pad after a single
        flushing response -- confirmed empirically, exactly one push
        attempt ever logged for the affected pad for the rest of its
        lifetime -- so losing this race once means the branch never
        receives another buffer, and ``_teardown_webrtc_transport``'s
        own protection (which waits for *a* push attempt that will now
        never come) times out after 5s, permanently, on every
        subsequent reconnect attempt against the same stuck pad. Holding
        any premature push at the tee's own pad until every transport
        element is confirmed PLAYING makes the race structurally
        impossible rather than merely unlikely -- no sleep, no timing
        assumption, a real verified condition."""
        Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()
        elements = list(self._transport_elements)

        def _all_playing() -> bool:
            for element in elements:
                change_return, state, _pending = element.get_state(0)
                if change_return == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError(
                        f"Camera {self._camera_id}: transport element "
                        f"{element.get_name()} failed to reach PLAYING during activation"
                    )
                if state != Gst.State.PLAYING:
                    return False
            return True

        elapsed = 0.0
        interval = 0.02
        try:
            while not await self._run_on_mainloop(_all_playing):
                await asyncio.sleep(interval)
                elapsed += interval
                if elapsed >= timeout_seconds:
                    raise TimeoutError(
                        f"Camera {self._camera_id}: transport branch did not reach "
                        f"PLAYING within {timeout_seconds}s"
                    )
        finally:

            def _release_activation_block() -> None:
                if (
                    self._activation_block_probe_id is not None
                    and self._transport_tee_pad is not None
                ):
                    self._transport_tee_pad.remove_probe(self._activation_block_probe_id)
                self._activation_block_probe_id = None

            await self._run_on_mainloop(_release_activation_block)

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

    # -- Teardown ---------------------------------------------------------

    async def teardown(self) -> None:
        """Removes this camera's branch entirely (camera unregistered/
        disconnected) -- unlike ``handle_offer()``'s rebuilds, this is a
        one-way trip, not called again afterward. Still serialized under
        ``self._rebuild_lock`` (see that field's own docstring) so this
        can never race an in-flight reconnect's own teardown/build of the
        same transport pad."""
        async with self._rebuild_lock:
            # Handles the RTP-buffer probe + payloader/webrtc_caps/
            # webrtcbin (including blocking the transport tee pad first)
            # -- a no-op if no browser is currently connected.
            await self._teardown_webrtc_transport()

            def _teardown_chain() -> None:
                Gst, _GstWebRTC, _GstSdp, _GstVideo = _import_gst()

                if self._annotate_probe_id is not None and self._annotate_probe_target is not None:
                    self._annotate_probe_target.remove_probe(self._annotate_probe_id)
                self._annotate_probe_id = None
                self._annotate_probe_target = None
                self._renderer = None

                # Sink-to-source, the reverse of construction order:
                # NULLing an upstream element (e.g. the queue right after
                # the SGIE tee) while its downstream neighbors are still
                # PLAYING can deadlock a streaming thread mid-push --
                # hardware-confirmed during repeated delete/re-register
                # cycles (real hardware bug: the GLib main-loop thread
                # wedged inside this exact loop, freezing every
                # subsequent pipeline mutation, including unrelated
                # cameras, since it is the only thread that services
                # AsyncBridge.schedule_on_mainloop()). GStreamer's own
                # application manual documents this ordering requirement
                # when removing elements from a running pipeline.
                for element in reversed(self._elements):
                    element.set_state(Gst.State.NULL)
                for element in self._elements:
                    self._pipeline.remove(element)
                self._elements = []

                if self._sgie_tee_pad is not None:
                    self._sgie_tee.release_request_pad(self._sgie_tee_pad)
                    self._sgie_tee_pad = None

                self._output_tee = None
                self._annotated_encoder = None
                self._webrtcbin = None

            await self._run_on_mainloop(_teardown_chain)

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
