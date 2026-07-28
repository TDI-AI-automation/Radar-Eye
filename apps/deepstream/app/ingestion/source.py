"""RTSP source bin construction and lifecycle (DEEPSTREAM_PIPELINE_SPEC.md Stage 1-2).

GStreamer/DeepStream element wiring only -- reconnect *policy* (backoff
timing, retry loop, event emission) intentionally lives in
``runtime.py``/``runtime_adapter.py`` instead, so that orchestration logic
stays testable without the GStreamer/DeepStream SDK (absent on non-Jetson
dev machines; confirmed unavailable in the original RM-11 dev environment,
though present and used for real hardware verification on this bench --
see test_source.py). This module is the one piece of RM-11 that can only
be exercised on real Jetson/DeepStream hardware.

Element chain per camera (Jetson hardware decode):
    rtspsrc -> rtph264depay -> h264parse -> nvv4l2decoder -> tee ->
        { tier1-raw-queue -> tier1-raw-sink (Tier 1 stub terminator)
        , valve -> [ghost src pad] (Tier 2 / AI path)
        }

RM-12 Camera Runtime, Decision 2 (valve-gating amendment): every source bin
owns one ``valve`` element, permanently present, positioned as the very
last element before the bin's ghost pad. This is the *only* mechanism
Camera Runtime will ever use to enable/disable AI for a camera (a later
milestone controls it -- see runtime.py's future EnableAI/DisableAI
command handling). This milestone only makes the valve physically exist,
discoverable by name via ``bin_.get_by_name(valve_element_name(camera_id))``,
and permanently open (``drop=False``) -- the pipeline's observable behavior
must be byte-for-byte identical to before this element existed. The ghost
pad is linked to a ``nvstreammux`` request sink pad by the caller
(``pipeline/builder.py``), which owns the shared streammux instance --
unaffected by this change; the streammux link target is still the bin's
one ghost pad, now sourced from the valve instead of the decoder directly.

RM-12 Camera Runtime, Step 2 (Frame Distributor): the bin also owns one
Tier 1 ``tee`` (see ``pipeline/frame_distributor.py``), positioned between
the decoder and the valve so the raw, pre-AI frame resource is
structurally independent of the valve's state -- toggling AI never affects
Tier 1. This milestone only builds the raw branch's stub terminator
(``tier1-raw-queue`` -> ``tier1-raw-sink``, safely draining, applying no
backpressure); no real Tier 1 consumer exists yet (see
``frame_distributor.Tier1FrameConsumer``). The AI path's element count and
behavior are otherwise unchanged: decoder now feeds the tee instead of the
valve directly, and the tee's other branch feeds the valve exactly as the
decoder used to.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from apps.deepstream.app.ingestion.camera_registry import CameraSource
from apps.deepstream.app.pipeline.frame_distributor import attach_tier1_branch

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


def valve_element_name(camera_id: uuid.UUID) -> str:
    """The AI-gating valve's element name within one camera's source bin --
    the discoverable handle a future milestone (Runtime Supervisor's
    EnableAI/DisableAI command handling) will use to find and toggle it via
    ``bin_.get_by_name(valve_element_name(camera_id))``. Named as its own
    function rather than inlined so both this module and that future
    caller derive the same name from one place."""
    return f"ai-valve-{camera_id}"


def build_source_bin(source: CameraSource, *, latency_ms: int = 200) -> Any:
    """Construct one camera's decode bin. Returns a ``Gst.Bin`` with a ghost
    src pad named ``src`` carrying decoded (NVMM) frames.

    ``latency_ms`` -- RM-11.SIV Decision B: config-driven
    (``DeepStreamSettings.rtsp_default_latency_ms``) rather than hardcoded;
    defaults preserved for any direct caller (e.g. tests).

    Raises whatever the DeepStream/GStreamer SDK raises on missing plugins
    (e.g. ``nvv4l2decoder`` requires the Jetson multimedia API) -- there is
    no software-decode fallback (DEEPSTREAM_PIPELINE_SPEC.md's Architecture
    Constraints prohibit OpenCV production pipelines; TensorRT/DeepStream is
    mandatory, INV-002/INV-003).

    RM-12 Camera Runtime, Decision 2: the bin now also owns one ``valve``
    element (see ``valve_element_name``), permanently open
    (``drop=False``) as of this milestone -- no caller may rely on it being
    closeable yet.

    RM-12 Camera Runtime, Step 2: the bin also owns one Tier 1 ``tee`` (see
    ``pipeline/frame_distributor.py``), positioned between the decoder and
    the valve, plus that tee's stub raw-branch terminator. The AI path
    (tee -> valve -> ghost pad) is otherwise byte-for-byte identical to
    before the tee existed.
    """
    Gst = _import_gst()

    bin_name = f"source-bin-{source.camera_id}"
    bin_ = Gst.Bin.new(bin_name)

    rtspsrc = Gst.ElementFactory.make("rtspsrc", f"rtspsrc-{source.camera_id}")
    depay = Gst.ElementFactory.make("rtph264depay", f"depay-{source.camera_id}")
    parse = Gst.ElementFactory.make("h264parse", f"parse-{source.camera_id}")
    decoder = Gst.ElementFactory.make("nvv4l2decoder", f"decoder-{source.camera_id}")
    valve = Gst.ElementFactory.make("valve", valve_element_name(source.camera_id))

    for name, element in (
        ("rtspsrc", rtspsrc),
        ("rtph264depay", depay),
        ("h264parse", parse),
        ("nvv4l2decoder", decoder),
        ("valve", valve),
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
    rtspsrc.set_property("latency", latency_ms)
    valve.set_property("drop", False)

    depay.link(parse)
    parse.link(decoder)

    tee = attach_tier1_branch(Gst, bin_, decoder, source.camera_id)
    ai_branch_pad = tee.get_request_pad("src_%u")
    if ai_branch_pad is None:
        raise RuntimeError(f"Failed to request tee src pad (AI branch) for {bin_name}")
    valve_sink_pad = valve.get_static_pad("sink")
    if ai_branch_pad.link(valve_sink_pad) != Gst.PadLinkReturn.OK:
        raise RuntimeError(f"Failed to link tier1 tee to valve for {bin_name}")

    # rtspsrc has no static src pad (depends on the negotiated stream) --
    # link depay once rtspsrc announces its pad.
    def _on_pad_added(_element: Any, pad: Any) -> None:
        sink_pad = depay.get_static_pad("sink")
        if not sink_pad.is_linked():
            pad.link(sink_pad)

    rtspsrc.connect("pad-added", _on_pad_added)

    ghost_pad = Gst.GhostPad.new("src", valve.get_static_pad("src"))
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

    def build(self, *, latency_ms: int = 200) -> Any:
        self.bin = build_source_bin(self.camera, latency_ms=latency_ms)
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
