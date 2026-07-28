"""Per-camera Tier 1 raw-frame fan-out (RM-12 Camera Runtime Step 2: Frame
Distributor).

Positions one ``tee`` immediately after decode and before the AI valve
(``ingestion/source.py``'s Step 1 addition), so Tier 1 -- the raw,
pre-inference frame resource -- is structurally independent of AI
enable/disable state, per RM-12's Two-Tier Frame Distribution Pattern, Part
A: Tier 1 never depends on AI, and toggling the valve must never affect
Tier 1 branches. Element chain per camera becomes:

    decoder -> tee -> { tier1-raw-queue -> tier1-raw-sink (this milestone's
                         stub terminator, see Tier1FrameConsumer)
                       , valve -> [ghost src pad] (AI path, unchanged)
                       }

This milestone builds the raw branch's terminator only -- a bounded, leaky
queue feeding a non-blocking ``fakesink``, mirroring the already-proven
backpressure-isolation shape from
``visualization/pipeline_builder.py``'s ``viz-queue`` -- plus a named,
unwired publish-interface contract for future Tier 1 consumers. No
transport, no buffering beyond the terminator queue's own bounds, no
subscriber registry: those are later milestones' (Media Publisher, Step 7)
job.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

_RAW_QUEUE_MAX_BUFFERS = 4
"""Same bounded, leaky, never-blocking shape as visualization/pipeline_builder.py's
viz-queue -- proven in that subsystem to isolate a tee's other branches from
a slow/stalled consumer. Small and fixed: bounded purely by buffer count
(max-size-bytes=0, max-size-time=0), combined with leaky=2 (downstream:
drops the oldest buffered frame, never blocks the tee)."""


class Tier1FrameConsumer(Protocol):
    """The contract a future Tier 1 consumer (raw preview, raw recording,
    Media Publisher) will implement to receive raw, pre-AI frames -- RM-12
    Two-Tier Pattern Part A: "any capability that only needs the picture
    attaches to Tier 1." Named seam only -- nothing in this module
    constructs, registers, or invokes an implementation of this protocol.
    The raw branch built by ``attach_tier1_branch`` terminates at a stub
    sink until a later milestone replaces that terminator with a real
    consumer."""

    def on_raw_frame(self, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        """Called with each raw decoded frame's ``Gst.Buffer``, once a real
        consumer exists. Not invoked by anything in this milestone."""
        ...


def tee_element_name(camera_id: uuid.UUID) -> str:
    """The Tier 1 tee's element name within one camera's source bin --
    mirrors ``source.valve_element_name``'s discoverability convention, for
    any future milestone that needs to find this tee by name (e.g. to
    replace the stub terminator branch with a real consumer) via
    ``bin_.get_by_name(tee_element_name(camera_id))``."""
    return f"tier1-tee-{camera_id}"


def attach_tier1_branch(Gst: Any, bin_: Any, upstream: Any, camera_id: uuid.UUID) -> Any:
    """Insert a Tier 1 tee between ``upstream`` (the decoder) and whatever
    ``upstream`` used to feed directly, adding a second, raw-stub branch off
    the tee. Returns the tee element -- the caller (``ingestion/source.py``)
    links the tee's remaining request pad to the valve, exactly where
    ``upstream.link(valve)`` used to link directly, keeping the AI path's
    element count and behavior otherwise unchanged.

    The raw branch (``tier1-raw-queue`` -> ``tier1-raw-sink``) terminates
    safely so pipeline timing is unaffected by this milestone: the queue is
    leaky/bounded (never blocks the tee), and the sink is a ``fakesink``
    with ``sync=False, async=False`` (consumes frames as fast as they
    arrive, applies no backpressure). No real consumer is attached -- see
    ``Tier1FrameConsumer``.
    """
    tee = Gst.ElementFactory.make("tee", tee_element_name(camera_id))
    raw_queue = Gst.ElementFactory.make("queue", f"tier1-raw-queue-{camera_id}")
    raw_sink = Gst.ElementFactory.make("fakesink", f"tier1-raw-sink-{camera_id}")

    for name, element in (("tee", tee), ("queue", raw_queue), ("fakesink", raw_sink)):
        if element is None:
            raise RuntimeError(
                f"Failed to create GStreamer element '{name}' for {tee_element_name(camera_id)}"
            )
        bin_.add(element)

    raw_queue.set_property("leaky", 2)  # downstream: drop oldest, never block
    raw_queue.set_property("max-size-buffers", _RAW_QUEUE_MAX_BUFFERS)
    raw_queue.set_property("max-size-bytes", 0)
    raw_queue.set_property("max-size-time", 0)
    raw_sink.set_property("sync", False)
    raw_sink.set_property("async", False)

    if not upstream.link(tee):
        raise RuntimeError(f"Failed to link decoder to tier1 tee for camera {camera_id}")
    if not raw_queue.link(raw_sink):
        raise RuntimeError(f"Failed to link tier1 raw queue to sink for camera {camera_id}")

    raw_branch_pad = tee.get_request_pad("src_%u")
    if raw_branch_pad is None:
        raise RuntimeError(f"Failed to request tee src pad (raw branch) for camera {camera_id}")
    queue_sink_pad = raw_queue.get_static_pad("sink")
    if raw_branch_pad.link(queue_sink_pad) != Gst.PadLinkReturn.OK:
        raise RuntimeError(f"Failed to link tier1 tee to raw queue for camera {camera_id}")

    return tee
