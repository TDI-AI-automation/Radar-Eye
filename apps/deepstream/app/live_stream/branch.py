"""CameraHlsBranch -- one camera's permanent AI-annotated low-latency
MPEG-TS output branch (ADR-032; class name predates the HLS->MPEG-TS
transport swap, kept to avoid a churny rename across manager.py/tests).

Built once when a camera connects, torn down once when it disconnects --
mirrors ``apps/deepstream/app/visualization/pipeline_builder.py``'s
``VisualizationPipelineBuilder`` almost exactly (same OSD/encode chain,
same disable-passthrough fix, same fail-fast construction discipline),
swapping that module's ``rtph264pay -> udpsink`` (RTSP, for an operator's
VLC client) for ``mpegtsmux -> tcpserversink`` (a persistent local TCP
broadcast, for ``apps.api`` to relay to browsers over WebSocket -- see
``apps/api/app/routers/live_video.py``). AI-annotated-only (ADR-030): a
single input chain, taps the AI pipeline's SGIE tee, no raw passthrough.

No WebRTC, no HLS, no per-browser-connection state inside DeepStream at
all. ``tcpserversink`` accepts any number of simultaneous TCP clients
natively (built-in multi-client fan-out, GStreamer's own mechanism, not
something this code manages) -- apps.api holds one persistent TCP
connection per camera and relays its bytes to however many authenticated
browser WebSocket clients are watching. Connecting, refreshing, or
adding more browser viewers touches nothing here at all -- the branch is
built once at camera-add and never mutated again until camera-remove.

Element construction/teardown must run on the GLib main-loop thread
(``AsyncBridge.schedule_on_mainloop``, via ``manager.py``) -- both
``build()`` and ``teardown()`` are synchronous, matching
``VisualizationPipelineBuilder``'s own convention; there is no
async/promise-based negotiation left to bridge.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.deepstream.app.config import LiveStreamSettings, VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.visualization.osd_renderer import DeepStreamOverlayRenderer
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


class CameraHlsBranch:
    def __init__(
        self,
        camera_id: uuid.UUID,
        camera_name: str,
        *,
        streammux_width: int,
        streammux_height: int,
        tcp_port: int,
        live_settings: LiveStreamSettings,
        visualization_settings: VisualizationSettings,
        track_annotations: TrackAnnotationRegistry,
        instrumentation: PerformanceInstrumentation | None,
    ) -> None:
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._width = streammux_width
        self._height = streammux_height
        self._tcp_port = tcp_port
        self._settings = live_settings
        self._visualization_settings = visualization_settings
        self._track_annotations = track_annotations
        self._instrumentation = instrumentation

        self._elements: list[Any] = []
        self._sgie_tee_pad: Any = None
        self._renderer: DeepStreamOverlayRenderer | None = None
        self._annotate_probe_target: Any = None
        self._annotate_probe_id: int | None = None

    def build(self, pipeline: Any, sgie_tee: Any) -> None:
        """Constructs and links the full low-latency branch off
        ``sgie_tee``: ``queue -> nvvideoconvert(RGBA) -> [annotate probe]
        -> nvdsosd -> nvvideoconvert(NV12) -> nvv4l2h264enc -> h264parse
        -> mpegtsmux -> tcpserversink``. Raises immediately on any
        construction/link failure -- never returns a half-built branch
        (same discipline as ``VisualizationPipelineBuilder.build()``)."""
        Gst = _import_gst()

        queue = self._make(Gst, "queue", f"live-osd-queue-{self._camera_id}")
        queue.set_property("leaky", 2)  # downstream: drop oldest, never block
        queue.set_property("max-size-buffers", 4)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)

        # disable-passthrough is required, not optional -- see
        # VisualizationPipelineBuilder.build()'s identical comment for the
        # hardware-confirmed "NVMM memory corrupted by nvosd after tee"
        # root cause this avoids.
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
        # iframeinterval/idrinterval: both set to the same ~1s cadence, not
        # just iframeinterval -- see docs/DEEPSTREAM_PIPELINE_SPEC.md's
        # latency investigation note (2026-08-16): idrinterval, left at its
        # default (256), is the property that actually governs when a
        # newly-attaching decoder can start clean playback -- iframeinterval
        # alone does not. A ~1s IDR cadence also bounds how long a
        # newly-connecting TCP client (tcpserversink's sync-method=
        # next-keyframe, below) waits before it receives any data at all.
        encoder.set_property("iframeinterval", self._visualization_settings.output_fps)
        encoder.set_property("idrinterval", self._visualization_settings.output_fps)
        # Match the camera's own real profile (Main) -- see
        # docs/DEEPSTREAM_PIPELINE_SPEC.md's tee-placement investigation;
        # avoids a mid-stream profile change on any future reconfiguration.
        encoder.set_property("profile", 2)  # GST_V4L2_H264_VIDENC_MAIN_PROFILE

        parser = self._make(Gst, "h264parse", f"live-annotated-parse-{self._camera_id}")
        parser.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe

        muxer = self._make(Gst, "mpegtsmux", f"live-tsmux-{self._camera_id}")
        # Defaults (pat/pmt-interval 9000 ticks @ 90kHz = 100ms) already
        # make PAT/PMT self-describing/join-anytime -- a client connecting
        # at an arbitrary moment gets a usable program table within
        # ~100ms, combined with the ~1s IDR cadence above for a decodable
        # picture. No property overrides needed.

        tcpsink = self._make(Gst, "tcpserversink", f"live-tcpsink-{self._camera_id}")
        tcpsink.set_property("host", self._settings.tcp_host)
        tcpsink.set_property("port", self._tcp_port)
        # next-keyframe: a newly-connecting TCP client (apps.api, on
        # behalf of a newly-connecting browser) receives nothing until
        # the next keyframe, then a clean start -- never a partial/
        # undecodable prefix. tcpserversink's own multi-client fan-out
        # (not GStreamer pad linking) is what lets any number of
        # apps.api connections attach/detach without this branch ever
        # being touched.
        tcpsink.set_property("sync-method", 1)  # next-keyframe
        tcpsink.set_property("sync", False)
        tcpsink.set_property("async", False)

        for element in (queue, convert_in, caps_rgba, osd, convert_out, caps_nv12, encoder, parser):
            pipeline.add(element)
            self._elements.append(element)
        pipeline.add(muxer)
        self._elements.append(muxer)
        pipeline.add(tcpsink)
        self._elements.append(tcpsink)

        self._link(queue, convert_in)
        self._link(convert_in, caps_rgba)
        self._link(caps_rgba, osd)
        self._link(osd, convert_out)
        self._link(convert_out, caps_nv12)
        self._link(caps_nv12, encoder)
        self._link(encoder, parser)

        mux_sink_pad = muxer.get_request_pad("sink_%d")
        if mux_sink_pad is None:
            raise RuntimeError(f"Failed to request mpegtsmux sink pad for camera {self._camera_id}")
        if parser.get_static_pad("src").link(mux_sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(
                f"Failed to link h264parse to mpegtsmux for camera {self._camera_id}"
            )
        self._link(muxer, tcpsink)

        tee_pad = sgie_tee.get_request_pad("src_%u")
        if tee_pad is None:
            raise RuntimeError(f"Failed to request SGIE tee pad for camera {self._camera_id}")
        self._sgie_tee_pad = tee_pad
        if tee_pad.link(queue.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            raise RuntimeError(
                f"Failed to link SGIE tee to HLS branch for camera {self._camera_id}"
            )

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
        if self._annotate_probe_id is None:
            raise RuntimeError(
                f"Failed to attach the HLS annotate probe for camera {self._camera_id}"
            )

        for element in self._elements:
            element.sync_state_with_parent()

    def teardown(self, pipeline: Any) -> None:
        """Deterministic shutdown -- same ordering discipline as
        ``VisualizationPipelineBuilder.teardown()``: NULL sink-to-source
        before removing, release the SGIE tee's request pad last."""
        Gst = _import_gst()

        if self._annotate_probe_id is not None and self._annotate_probe_target is not None:
            self._annotate_probe_target.remove_probe(self._annotate_probe_id)
        self._annotate_probe_id = None
        self._annotate_probe_target = None
        self._renderer = None

        for element in reversed(self._elements):
            element.set_state(Gst.State.NULL)
        for element in self._elements:
            pipeline.remove(element)
        self._elements = []

        if self._sgie_tee_pad is not None:
            tee = self._sgie_tee_pad.get_parent()
            if tee is not None:
                tee.release_request_pad(self._sgie_tee_pad)
            self._sgie_tee_pad = None

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
