"""RTSP source bin construction and lifecycle (DEEPSTREAM_PIPELINE_SPEC.md Stage 1-2).

GStreamer/DeepStream element wiring only -- reconnect *policy* (backoff
timing, retry loop, event emission) intentionally lives in
``runtime.py``/``runtime_adapter.py`` instead, so that orchestration logic
stays testable without the GStreamer/DeepStream SDK (absent on non-Jetson
dev machines; confirmed unavailable in this environment). This module is the
one piece of RM-11 that can only be exercised on real Jetson/DeepStream
hardware.

Element chain per camera (Jetson hardware decode):
    rtspsrc -> rtph264depay -> h264parse -> nvv4l2decoder -> [ghost src pad]
The ghost pad is linked to a ``nvstreammux`` request sink pad by the caller
(``pipeline/builder.py``), which owns the shared streammux instance.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from apps.deepstream.app.ingestion.camera_registry import CameraSource

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


def build_source_bin(source: CameraSource) -> Any:
    """Construct one camera's decode bin. Returns a ``Gst.Bin`` with a ghost
    src pad named ``src`` carrying decoded (NVMM) frames.

    Raises whatever the DeepStream/GStreamer SDK raises on missing plugins
    (e.g. ``nvv4l2decoder`` requires the Jetson multimedia API) -- there is
    no software-decode fallback (DEEPSTREAM_PIPELINE_SPEC.md's Architecture
    Constraints prohibit OpenCV production pipelines; TensorRT/DeepStream is
    mandatory, INV-002/INV-003).
    """
    Gst = _import_gst()

    bin_name = f"source-bin-{source.camera_id}"
    bin_ = Gst.Bin.new(bin_name)

    rtspsrc = Gst.ElementFactory.make("rtspsrc", f"rtspsrc-{source.camera_id}")
    depay = Gst.ElementFactory.make("rtph264depay", f"depay-{source.camera_id}")
    parse = Gst.ElementFactory.make("h264parse", f"parse-{source.camera_id}")
    decoder = Gst.ElementFactory.make("nvv4l2decoder", f"decoder-{source.camera_id}")

    for name, element in (
        ("rtspsrc", rtspsrc),
        ("rtph264depay", depay),
        ("h264parse", parse),
        ("nvv4l2decoder", decoder),
    ):
        if element is None:
            raise RuntimeError(f"Failed to create GStreamer element '{name}' for {bin_name}")
        bin_.add(element)

    rtspsrc.set_property("location", source.rtsp_url)
    if source.transport:
        # rtspsrc.protocols is a GstRTSPLowerTrans flags value (e.g. "tcp"/"udp");
        # left unconstrained per DATABASE_SCHEMA.md -- no architecture document
        # defines camera_stream_profiles.transport's value set (RM-03 design note).
        rtspsrc.set_property("protocols", source.transport)
    rtspsrc.set_property("latency", 200)

    depay.link(parse)
    parse.link(decoder)

    # rtspsrc has no static src pad (depends on the negotiated stream) --
    # link depay once rtspsrc announces its pad.
    def _on_pad_added(_element: Any, pad: Any) -> None:
        sink_pad = depay.get_static_pad("sink")
        if not sink_pad.is_linked():
            pad.link(sink_pad)

    rtspsrc.connect("pad-added", _on_pad_added)

    ghost_pad = Gst.GhostPad.new("src", decoder.get_static_pad("src"))
    bin_.add_pad(ghost_pad)

    return bin_


@dataclass
class RtspSource:
    """One camera's source bin plus enough identity to match bus messages
    against it. Owns no reconnect timing -- see module docstring."""

    camera: CameraSource
    bin: Any = None

    @property
    def camera_id(self) -> uuid.UUID:
        return self.camera.camera_id

    def build(self) -> Any:
        self.bin = build_source_bin(self.camera)
        return self.bin

    def is_failure_message(self, message: Any) -> bool:
        """True if ``message`` is a GST_MESSAGE_ERROR or GST_MESSAGE_EOS
        originating from an element inside this source's bin."""
        Gst = _import_gst()
        if message.type not in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
            return False
        src = message.src
        return self.bin is not None and bool(src) and self._owns(src)

    def _owns(self, element: Any) -> bool:
        parent = element
        while parent is not None:
            if parent == self.bin:
                return True
            parent = parent.get_parent()
        return False
