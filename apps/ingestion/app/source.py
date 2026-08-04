"""RTSP source bin construction -- Camera Ingestion's entire GStreamer
scope (ADR-028): ``rtspsrc -> rtph264depay -> h264parse -> tee``. Nothing
else. The tee is the "Encoded Split" -- every local consumer of this
camera's bitstream (today: the RTSP republish relay; later: additional
in-process taps if ever needed) requests its own pad from it rather
than the bin exposing a single ghost src pad, following this codebase's
established tee-element-by-name convention (``apps/deepstream/app/
pipeline/frame_distributor.py``'s ``tee_element_name``/``get_by_name``/
``get_request_pad`` shape).

No decode, no NVDEC, no CUDA, no valve, no streammux, no inference, no
webrtcbin, no encoder -- those all belonged to the old, DeepStream-owned
ingestion path this service replaces (``apps/deepstream/app/ingestion/
source.py``, not migrated, not imported). This module's own output --
the camera's original, unmodified encoded H.264 access units -- is
handed directly to ``shared.media_transport.rtsp.RtspMediaPublisher.
publish()`` by ``runtime.py``; nothing else happens to it here.
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


def tee_element_name(camera_id: uuid.UUID) -> str:
    """Name of the per-camera Encoded Split tee inside its ingestion
    bin, discoverable via ``bin_.get_by_name(tee_element_name(camera_id))``."""
    return f"encoded-split-{camera_id}"


def build_source_bin(source: CameraSource, *, latency_ms: int = 200) -> Any:
    """Construct one camera's ingestion bin: ``rtspsrc -> rtph264depay ->
    h264parse -> tee``. No ghost pad -- callers request their own pad
    directly from the tee (named per ``tee_element_name``) carrying the
    camera's original encoded H.264 access units. No decode, no
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
    tee = Gst.ElementFactory.make("tee", tee_element_name(source.camera_id))

    for name, element in (
        ("rtspsrc", rtspsrc),
        ("rtph264depay", depay),
        ("h264parse", parse),
        ("tee", tee),
    ):
        if element is None:
            raise RuntimeError(f"Failed to create GStreamer element '{name}' for {bin_name}")
        bin_.add(element)

    rtspsrc.set_property("location", source.rtsp_url)
    if source.transport:
        rtspsrc.set_property("protocols", source.transport)
    rtspsrc.set_property("latency", latency_ms)

    depay.link(parse)
    parse.link(tee)

    # rtspsrc has no static src pad (depends on the negotiated stream) --
    # link depay once rtspsrc announces its pad.
    def _on_pad_added(_element: Any, pad: Any) -> None:
        sink_pad = depay.get_static_pad("sink")
        if not sink_pad.is_linked():
            pad.link(sink_pad)

    rtspsrc.connect("pad-added", _on_pad_added)

    return bin_


def request_split_pad(bin_: Any, camera_id: uuid.UUID) -> Any:
    """Requests a new pad from the bin's Encoded Split tee and ghosts it
    out to the bin's own boundary. A pad belonging to an element inside
    a child ``Gst.Bin`` cannot be linked directly to an element added to
    the parent pipeline (e.g. by a ``MediaPublisher``) -- crossing a bin
    boundary requires a ghost pad, the same reason this module's single
    consumer used one before this tee existed. Returns the ghost pad;
    release it with ``release_split_pad`` when the caller is done."""
    Gst = _import_gst()
    tee = bin_.get_by_name(tee_element_name(camera_id))
    tee_pad = tee.get_request_pad("src_%u")
    if tee_pad is None:
        raise RuntimeError(f"Failed to request Encoded Split tee pad for camera {camera_id}")
    ghost_pad = Gst.GhostPad.new(f"split-{tee_pad.get_name()}", tee_pad)
    if not bin_.add_pad(ghost_pad):
        raise RuntimeError(f"Failed to ghost Encoded Split tee pad for camera {camera_id}")
    ghost_pad.set_active(True)
    return ghost_pad


def release_split_pad(bin_: Any, camera_id: uuid.UUID, ghost_pad: Any) -> None:
    """Reverses ``request_split_pad``: unghosts ``ghost_pad`` and
    releases the underlying Encoded Split tee request pad."""
    tee = bin_.get_by_name(tee_element_name(camera_id))
    target = ghost_pad.get_target()
    bin_.remove_pad(ghost_pad)
    if tee is not None and target is not None:
        tee.release_request_pad(target)


@dataclass
class IngestedSource:
    """One camera's active source bin plus enough identity to match bus
    messages against it. Owns no reconnect timing -- see ``runtime.py``."""

    camera: CameraSource
    bin: Any = None
    split_pad: Any = None
    """The Encoded Split tee's request pad handed to the RTSP publisher
    -- kept so teardown can release it explicitly (see runtime.py),
    matching this codebase's tee-request-pad release discipline."""

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
