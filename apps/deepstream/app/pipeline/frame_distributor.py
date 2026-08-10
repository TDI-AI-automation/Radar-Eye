"""Per-camera frame/bitstream fan-out (RM-12 Camera Runtime Step 2: Frame
Distributor; extended for the Live Streaming architecture reset with a
second, pre-decode bitstream tee).

Two independent tees, at two different points in the per-camera source
bin, per ``docs/DEEPSTREAM_PIPELINE_SPEC.md``'s "every media
representation exists exactly once" principle -- each tap point has
exactly one producer, shared by however many consumers attach to it:

    rtspsrc -> depay -> h264parse -> bitstream-tee -> { bitstream-queue ->
        bitstream-sink (terminator; media_publisher/bitstream.py's
        BitstreamPublisher attaches a probe here -- encoded H.264, no
        decode) , decoder }
    decoder -> tier1-tee -> { tier1-raw-queue -> tier1-raw-sink
        (terminator; media_publisher/tier1.py's Tier1Publisher attaches a
        probe here -- decoded NVMM frames) , valve -> [ghost src pad]
        (AI path, unchanged) }

Positions the (existing) Tier 1 tee immediately after decode and before
the AI valve (``ingestion/source.py``'s Step 1 addition), so Tier 1 --
the raw, pre-inference frame resource -- is structurally independent of
AI enable/disable state, per RM-12's Two-Tier Frame Distribution
Pattern, Part A: Tier 1 never depends on AI, and toggling the valve must
never affect Tier 1 branches. The (new) bitstream tee sits earlier
still, before any decode at all, so Live Streaming's raw passthrough
never depends on decode/AI either.

This module builds each tee's stub-branch terminator only -- a bounded,
leaky queue feeding a non-blocking ``fakesink``, mirroring the
already-proven backpressure-isolation shape from
``visualization/pipeline_builder.py``'s ``viz-queue``. No transport, no
subscriber registry lives here: that's ``media_publisher/tier1.py``'s and
``media_publisher/bitstream.py``'s job, which find their branch by name
and attach/detach their own probe on it -- this module is unchanged by,
and has no dependency on, either subsystem.
"""

from __future__ import annotations

import uuid
from typing import Any

_RAW_QUEUE_MAX_BUFFERS = 4
"""Same bounded, leaky, never-blocking shape as visualization/pipeline_builder.py's
viz-queue -- proven in that subsystem to isolate a tee's other branches from
a slow/stalled consumer. Small and fixed: bounded purely by buffer count
(max-size-bytes=0, max-size-time=0), combined with leaky=2 (downstream:
drops the oldest buffered frame, never blocks the tee)."""


def tee_element_name(camera_id: uuid.UUID) -> str:
    """The Tier 1 tee's element name within one camera's source bin --
    mirrors ``source.valve_element_name``'s discoverability convention, for
    any future milestone that needs to find this tee by name (e.g. to
    replace the stub terminator branch with a real consumer) via
    ``bin_.get_by_name(tee_element_name(camera_id))``."""
    return f"tier1-tee-{camera_id}"


def tier1_raw_queue_element_name(camera_id: uuid.UUID) -> str:
    """The Tier 1 raw branch's queue element name -- the discoverable
    attachment point ``media_publisher/tier1.py``'s ``Tier1Publisher`` uses
    to find and probe it via
    ``bin_.get_by_name(tier1_raw_queue_element_name(camera_id))``, mirroring
    ``valve_element_name``'s/``tee_element_name``'s discoverability
    convention."""
    return f"tier1-raw-queue-{camera_id}"


def tier1_raw_sink_element_name(camera_id: uuid.UUID) -> str:
    return f"tier1-raw-sink-{camera_id}"


def attach_tier1_branch(Gst: Any, bin_: Any, upstream: Any, camera_id: uuid.UUID) -> Any:
    """Insert a Tier 1 tee between ``upstream`` (the decoder) and whatever
    ``upstream`` used to feed directly, adding a second, raw-stub branch off
    the tee. Returns the tee element -- the caller (``ingestion/source.py``)
    links the tee's remaining request pad to the valve, exactly where
    ``upstream.link(valve)`` used to link directly, keeping the AI path's
    element count and behavior otherwise unchanged.

    The raw branch (``tier1-raw-queue`` -> ``tier1-raw-sink``) terminates
    safely so pipeline timing is unaffected: the queue is leaky/bounded
    (never blocks the tee), and the sink is a ``fakesink`` with
    ``sync=False, async=False`` (consumes frames as fast as they arrive,
    applies no backpressure) -- true whether or not a Tier1Publisher probe
    is currently attached to the queue's src pad.
    """
    tee = Gst.ElementFactory.make("tee", tee_element_name(camera_id))
    raw_queue = Gst.ElementFactory.make("queue", tier1_raw_queue_element_name(camera_id))
    raw_sink = Gst.ElementFactory.make("fakesink", tier1_raw_sink_element_name(camera_id))

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


def bitstream_tee_element_name(camera_id: uuid.UUID) -> str:
    """The bitstream tee's element name within one camera's source bin --
    mirrors ``tee_element_name``'s discoverability convention."""
    return f"bitstream-tee-{camera_id}"


def bitstream_queue_element_name(camera_id: uuid.UUID) -> str:
    """The bitstream branch's queue element name -- the discoverable
    attachment point ``media_publisher/bitstream.py``'s
    ``BitstreamPublisher`` uses to find and probe it via
    ``bin_.get_by_name(bitstream_queue_element_name(camera_id))``, mirroring
    ``tier1_raw_queue_element_name``'s convention."""
    return f"bitstream-queue-{camera_id}"


def bitstream_sink_element_name(camera_id: uuid.UUID) -> str:
    return f"bitstream-sink-{camera_id}"


def attach_bitstream_branch(Gst: Any, bin_: Any, upstream: Any, camera_id: uuid.UUID) -> Any:
    """Insert a tee between ``upstream`` (``h264parse``, pre-decode) and
    whatever ``upstream`` used to feed directly (the decoder), adding a
    second, stub branch off the tee. Returns the tee element -- the
    caller (``ingestion/source.py``) links the tee's remaining request
    pad to the decoder, exactly where ``upstream.link(decoder)`` used to
    link directly, keeping the decode/AI path's element count and
    behavior otherwise unchanged.

    This is **bitstream distribution**, not frame distribution -- the
    tee sits before any decode, fanning out the camera's original,
    still-encoded H.264 access units. Deliberately not named "Tier 0":
    Tier 1/Tier 2 (this module's other tee, and ``media_publisher/tier2.py``)
    are decoded/annotated *frame* tiers; this is a structurally different
    thing (compressed bitstream, one producer -- ``h264parse`` -- shared
    by every consumer that taps this tee, per the "every media
    representation exists exactly once" principle in
    ``docs/DEEPSTREAM_PIPELINE_SPEC.md``). Confirmed on real hardware
    that a shared, single ``h264parse`` feeding a tee here is correct and
    sufficient -- AU-aligned output, identical caps/SPS-PPS and
    timestamp continuity on every branch, ``nvv4l2decoder`` unaffected
    immediately downstream of it. No reason found to duplicate the
    parser per consumer.

    The stub branch (``bitstream-queue`` -> ``bitstream-sink``)
    terminates safely so pipeline timing is unaffected: same
    leaky/bounded queue + non-blocking ``fakesink`` shape as
    ``attach_tier1_branch``, true whether or not a BitstreamPublisher
    probe is currently attached to the queue's src pad.
    """
    tee = Gst.ElementFactory.make("tee", bitstream_tee_element_name(camera_id))
    queue = Gst.ElementFactory.make("queue", bitstream_queue_element_name(camera_id))
    sink = Gst.ElementFactory.make("fakesink", bitstream_sink_element_name(camera_id))

    for name, element in (("tee", tee), ("queue", queue), ("fakesink", sink)):
        if element is None:
            raise RuntimeError(
                f"Failed to create GStreamer element '{name}' for "
                f"{bitstream_tee_element_name(camera_id)}"
            )
        bin_.add(element)

    queue.set_property("leaky", 2)  # downstream: drop oldest, never block
    queue.set_property("max-size-buffers", _RAW_QUEUE_MAX_BUFFERS)
    queue.set_property("max-size-bytes", 0)
    queue.set_property("max-size-time", 0)
    sink.set_property("sync", False)
    sink.set_property("async", False)

    if not upstream.link(tee):
        raise RuntimeError(f"Failed to link parser to bitstream tee for camera {camera_id}")
    if not queue.link(sink):
        raise RuntimeError(f"Failed to link bitstream queue to sink for camera {camera_id}")

    branch_pad = tee.get_request_pad("src_%u")
    if branch_pad is None:
        raise RuntimeError(
            f"Failed to request tee src pad (bitstream branch) for camera {camera_id}"
        )
    queue_sink_pad = queue.get_static_pad("sink")
    if branch_pad.link(queue_sink_pad) != Gst.PadLinkReturn.OK:
        raise RuntimeError(f"Failed to link bitstream tee to queue for camera {camera_id}")

    return tee
