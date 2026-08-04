"""RTSP source bin construction -- Camera Ingestion's entire GStreamer
scope (ADR-028): ``rtspsrc -> rtph264depay -> h264parse -> [ghost pad]``.

No decode, no NVDEC, no CUDA, no valve, no bitstream tee -- those all
belonged to the old, DeepStream-owned ingestion path this service
replaces (``apps/deepstream/app/ingestion/source.py``, not migrated,
not imported). This module's own output -- the camera's original,
unmodified encoded H.264 access units -- is handed directly to
``shared.media_transport.rtsp.RtspMediaPublisher.publish()`` by
``runtime.py``; nothing else happens to it here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.ingestion.app.camera_registry import CameraSource


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


def build_source_bin(source: CameraSource, *, latency_ms: int = 200) -> Any:
    """Construct one camera's ingestion bin. Returns a ``Gst.Bin`` with a
    ghost src pad named ``src`` carrying the camera's original encoded
    H.264 access units (``h264parse`` output) -- no decode, no
    conversion, no AI-gating element of any kind.

    Raises whatever the GStreamer SDK raises on missing plugins -- no
    fallback, matching every other source-bin-construction module in
    this codebase.
    """
    Gst = _import_gst()

    bin_name = f"ingest-bin-{source.camera_id}"
    bin_ = Gst.Bin.new(bin_name)

    rtspsrc = Gst.ElementFactory.make("rtspsrc", f"rtspsrc-{source.camera_id}")
    depay = Gst.ElementFactory.make("rtph264depay", f"depay-{source.camera_id}")
    parse = Gst.ElementFactory.make("h264parse", f"parse-{source.camera_id}")

    for name, element in (("rtspsrc", rtspsrc), ("rtph264depay", depay), ("h264parse", parse)):
        if element is None:
            raise RuntimeError(f"Failed to create GStreamer element '{name}' for {bin_name}")
        bin_.add(element)

    rtspsrc.set_property("location", source.rtsp_url)
    if source.transport:
        rtspsrc.set_property("protocols", source.transport)
    rtspsrc.set_property("latency", latency_ms)

    depay.link(parse)

    # rtspsrc has no static src pad (depends on the negotiated stream) --
    # link depay once rtspsrc announces its pad.
    def _on_pad_added(_element: Any, pad: Any) -> None:
        sink_pad = depay.get_static_pad("sink")
        if not sink_pad.is_linked():
            pad.link(sink_pad)

    rtspsrc.connect("pad-added", _on_pad_added)

    ghost_pad = Gst.GhostPad.new("src", parse.get_static_pad("src"))
    bin_.add_pad(ghost_pad)

    return bin_


@dataclass
class IngestedSource:
    """One camera's active source bin plus enough identity to match bus
    messages against it. Owns no reconnect timing -- see ``runtime.py``."""

    camera: CameraSource
    bin: Any = None

    @property
    def camera_id(self) -> uuid.UUID:
        return self.camera.camera_id

    def build(self, *, latency_ms: int = 200) -> Any:
        self.bin = build_source_bin(self.camera, latency_ms=latency_ms)
        return self.bin

    def is_failure_message(self, message: Any) -> bool:
        """True if ``message`` reports a GST_MESSAGE_ERROR or
        GST_MESSAGE_EOS originating from an element inside this
        source's bin."""
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
