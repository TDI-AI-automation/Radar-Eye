"""VisualizationPipelineBuilder -- constructs and tears down the
visualization branch's GStreamer elements, RM-11.SIV.

Everything downstream of the ``tee``'s visualization pad lives here:
``viz-queue -> nvvideoconvert -> capsfilter(RGBA) -> [annotate probe] ->
nvdsosd -> nvvideoconvert -> capsfilter(NV12) -> encoder -> h264parse ->
rtph264pay -> udpsink``. ``builder.py`` creates the ``tee`` itself (it's the
pipeline fork point, not visualization-specific) and only ever calls
``build()``/``teardown()`` here -- it never constructs a converter,
encoder, OSD, or payloader itself.

Backpressure: ``viz-queue`` is leaky (drops the oldest buffered frame
rather than blocking) and small, so a slow encoder/RTSP client can never
apply backpressure back through the ``tee`` onto the inference branch --
see ``_VIZ_QUEUE_MAX_BUFFERS``/``leaky`` below.

Self-validation (fail fast, before ``PLAYING``): every ``ElementFactory.
make()`` result and every ``link()`` return value is checked immediately,
inline, as each element is created/linked -- a failure raises right away
rather than being silently absorbed and only surfacing once the pipeline
reaches ``PLAYING``.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.deepstream.app.config import VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.stage_logging import get_stage_logger
from apps.deepstream.app.visualization.osd_renderer import DeepStreamOverlayRenderer
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

_logger = get_stage_logger("visualization")

_INTERNAL_UDP_PORT = 5400
"""Loopback-only relay port between the encoder branch and the RTSP
server's udpsrc-wrapping media factory (RM-11.SIV Phase 3) -- an internal
implementation detail, not the operator-facing port
(``visualization.rtsp_port``, the real RTSP/TCP port clients connect to)."""

_VIZ_QUEUE_MAX_BUFFERS = 4
"""Small and fixed -- bounded purely by buffer count (max-size-bytes=0,
max-size-time=0), combined with leaky=2 (downstream: drops the oldest
buffered frame to make room for the newest). Guarantees this queue can
never block the tee's push(), and therefore can never stall the inference
branch sharing the same tee."""


class VisualizationPipelineBuilder:
    def __init__(
        self,
        settings: VisualizationSettings,
        *,
        camera_id: uuid.UUID,
        camera_name: str,
        track_annotations: TrackAnnotationRegistry,
        instrumentation: PerformanceInstrumentation | None = None,
    ) -> None:
        self._settings = settings
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._track_annotations = track_annotations
        self._instrumentation = instrumentation
        self._elements: list[Any] = []
        self._tee_pad: Any = None
        self._probe_target_pad: Any = None
        self._probe_id: int | None = None
        self.renderer: DeepStreamOverlayRenderer | None = None
        self.udp_port = _INTERNAL_UDP_PORT

    def build(self, pipeline: Any, tee: Any) -> int:
        """Constructs and links the full visualization branch off ``tee``.
        Returns the internal UDP port the branch publishes H.264/RTP to
        (consumed by ``RtspStreamServer`` in Phase 3). Raises immediately
        on any construction/link failure -- never returns a half-built
        branch."""
        Gst = _import_gst()

        queue = self._make(Gst, "queue", "viz-queue")
        queue.set_property("leaky", 2)  # downstream: drop oldest, never block
        queue.set_property("max-size-buffers", _VIZ_QUEUE_MAX_BUFFERS)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)

        convert_in = self._make(Gst, "nvvideoconvert", "viz-convert-in")
        caps_rgba = self._make(Gst, "capsfilter", "viz-caps-rgba")
        caps_rgba.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM),format=RGBA"))

        osd = self._make(Gst, "nvdsosd", "viz-osd")

        convert_out = self._make(Gst, "nvvideoconvert", "viz-convert-out")
        caps_nv12 = self._make(Gst, "capsfilter", "viz-caps-nv12")
        caps_nv12.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM),format=NV12"))

        encoder = self._make(Gst, "nvv4l2h264enc", "viz-encoder")
        encoder.set_property("bitrate", self._settings.output_bitrate)

        parser = self._make(Gst, "h264parse", "viz-parse")

        payloader = self._make(Gst, "rtph264pay", "viz-pay")
        payloader.set_property("pt", 96)
        payloader.set_property("config-interval", 1)

        udpsink = self._make(Gst, "udpsink", "viz-udpsink")
        udpsink.set_property("host", "127.0.0.1")
        udpsink.set_property("port", self.udp_port)
        udpsink.set_property("sync", False)
        udpsink.set_property("async", False)

        self._elements = [
            queue,
            convert_in,
            caps_rgba,
            osd,
            convert_out,
            caps_nv12,
            encoder,
            parser,
            payloader,
            udpsink,
        ]
        for element in self._elements:
            pipeline.add(element)

        self._link(queue, convert_in)
        self._link(convert_in, caps_rgba)
        self._link(caps_rgba, osd)
        self._link(osd, convert_out)
        self._link(convert_out, caps_nv12)
        self._link(caps_nv12, encoder)
        self._link(encoder, parser)
        self._link(parser, payloader)
        self._link(payloader, udpsink)

        tee_pad = tee.get_request_pad("src_%u")
        if tee_pad is None:
            raise RuntimeError("Failed to request a src pad from the visualization tee")
        self._tee_pad = tee_pad
        queue_sink_pad = queue.get_static_pad("sink")
        if tee_pad.link(queue_sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError("Failed to link tee -> viz-queue")

        self.renderer = DeepStreamOverlayRenderer(
            self._settings,
            camera_id=self._camera_id,
            camera_name=self._camera_name,
            track_annotations=self._track_annotations,
            instrumentation=self._instrumentation,
        )
        self._probe_target_pad = convert_in.get_static_pad("src")
        self._probe_id = self._probe_target_pad.add_probe(
            Gst.PadProbeType.BUFFER, self.renderer.probe_callback
        )
        if self._probe_id is None:
            raise RuntimeError("Failed to attach the visualization annotate probe")

        return self.udp_port

    def teardown(self, pipeline: Any) -> None:
        """Deterministic shutdown -- see docs/DEEPSTREAM_PIPELINE_SPEC.md's
        Visualization Path section for the full rationale. Assumes no
        buffer is concurrently in flight through this branch (true both
        for full-runtime shutdown and for repeated build()/teardown()
        cycles in tests against a placeholder pipeline) -- live hot-toggle
        of visualization while inference continues uninterrupted is not a
        requirement of this milestone and is not implemented here."""
        Gst = _import_gst()

        if self._probe_id is not None and self._probe_target_pad is not None:
            self._probe_target_pad.remove_probe(self._probe_id)
        self._probe_id = None
        self._probe_target_pad = None

        for element in self._elements:
            element.set_state(Gst.State.NULL)
        for element in self._elements:
            pipeline.remove(element)
        self._elements = []

        if self._tee_pad is not None:
            tee = self._tee_pad.get_parent()
            if tee is not None:
                tee.release_request_pad(self._tee_pad)
            self._tee_pad = None

        self.renderer = None

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


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst
