"""Tier 2 (AI-annotated media) publisher -- RM-12 Camera Runtime Step 7.

Unlike Tier 1 (whose per-camera branch already exists from Step 2), Tier
2's per-camera branch does not exist until a camera is added: it lives
downstream of the shared ``nvstreamdemux`` element (``pipeline/builder.py``
creates that element once, camera-independently, exactly like it already
does for the SGIE tee) -- ``Tier2Publisher.on_camera_added()``/
``on_camera_removed()`` build/tear down each camera's own branch off it,
called synchronously and inline from ``DeepStreamPipeline.add_source()``/
``remove_source()``, mirroring ``VisualizationManager.initialize()``'s
exact calling convention (already-correctly-threaded by construction, no
separate ``AsyncBridge`` hop needed for construction/teardown -- only the
consumer-facing ``attach()``/``detach()`` probe lifecycle, inherited from
``_TieredPublisher``, goes through the bridge).

Availability is automatic, not something this module decides: a camera
whose AI valve (Step 1) is closed never feeds streammux/PGIE/Tracker/SGIE
in the first place, so ``nvstreamdemux``'s corresponding output pad simply
receives nothing while that camera is AI-disabled -- "Tier 2 available
only for AI-enabled cameras" falls out of the existing topology for free.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from apps.deepstream.app.media_publisher.base import GstBridge, _TieredPublisher
from apps.deepstream.app.media_publisher.interfaces import Tier2FrameConsumer

logger = logging.getLogger(__name__)

_QUEUE_MAX_BUFFERS = 4
"""Same bounded/leaky shape as Tier 1's raw-queue and visualization's
viz-queue -- a slow/absent Tier 2 consumer must never apply backpressure
back through nvstreamdemux into the shared PGIE/Tracker/SGIE path."""


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


def tier2_queue_element_name(camera_id: uuid.UUID) -> str:
    return f"tier2-queue-{camera_id}"


def tier2_sink_element_name(camera_id: uuid.UUID) -> str:
    return f"tier2-sink-{camera_id}"


@dataclass
class _Tier2Branch:
    queue: Any
    sink: Any
    demux_pad: Any


class Tier2Publisher(_TieredPublisher[Tier2FrameConsumer]):
    def __init__(self, bridge: GstBridge) -> None:
        super().__init__(bridge)
        self._branches: dict[uuid.UUID, _Tier2Branch] = {}
        self._demux_pads: dict[uuid.UUID, Any] = {}
        """nvstreamdemux's request src pad for a camera_id, kept for this
        publisher's *entire process lifetime* once requested -- never
        released on removal. See on_camera_removed()'s docstring: this
        mirrors DeepStreamPipeline.remove_source()'s identical,
        hardware-confirmed fix for the same class of bug (NVIDIA's own
        reference implementation and multiple NVIDIA Developer Forum
        threads: nvstreammux/nvstreamdemux request pads must be requested
        once and only ever linked/unlinked afterward, never dynamically
        released while the pipeline is live)."""
        self._gst_pipeline: Any = None

    def on_camera_added(
        self, gst_pipeline: Any, demux: Any, *, camera_id: uuid.UUID, pad_index: int
    ) -> None:
        """Builds this camera's Tier 2 branch: ``nvstreamdemux`` ->
        ``tier2-queue`` (bounded/leaky) -> ``tier2-sink`` (draining
        terminator, exactly like Tier 1's stub -- a real transport is
        future work). Idempotent: a camera already present is left alone
        (the reconnect path calls ``add_source()`` again for an
        already-known camera; this mirrors ``VisualizationManager``'s own
        "never re-initialize" guard). The queue/sink pair is rebuilt fresh
        each time (cheap, disposable); the demux's request pad itself is
        reused if this camera_id has ever been added before -- see
        ``_demux_pads``."""
        if camera_id in self._branches:
            return

        Gst = _import_gst()
        queue = Gst.ElementFactory.make("queue", tier2_queue_element_name(camera_id))
        sink = Gst.ElementFactory.make("fakesink", tier2_sink_element_name(camera_id))
        for name, element in (("queue", queue), ("fakesink", sink)):
            if element is None:
                raise RuntimeError(
                    f"Failed to create GStreamer element '{name}' for tier2 camera {camera_id}"
                )
            gst_pipeline.add(element)

        queue.set_property("leaky", 2)  # downstream: drop oldest, never block
        queue.set_property("max-size-buffers", _QUEUE_MAX_BUFFERS)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)
        sink.set_property("sync", False)
        sink.set_property("async", False)

        if not queue.link(sink):
            raise RuntimeError(f"Failed to link tier2 queue to sink for camera {camera_id}")

        demux_pad = self._demux_pads.get(camera_id)
        if demux_pad is None:
            demux_pad = demux.get_request_pad(f"src_{pad_index}")
            if demux_pad is None:
                demux_pad = demux.request_pad_simple(f"src_{pad_index}")
            if demux_pad is None:
                raise RuntimeError(
                    f"Failed to request nvstreamdemux src_{pad_index} for camera {camera_id}"
                )
            self._demux_pads[camera_id] = demux_pad
        queue_sink_pad = queue.get_static_pad("sink")
        if demux_pad.link(queue_sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(
                f"Failed to link nvstreamdemux to tier2 queue for camera {camera_id}"
            )

        queue.sync_state_with_parent()
        sink.sync_state_with_parent()

        self._gst_pipeline = gst_pipeline
        self._branches[camera_id] = _Tier2Branch(queue=queue, sink=sink, demux_pad=demux_pad)

    def on_camera_removed(self, camera_id: uuid.UUID) -> None:
        """Deterministic teardown order: remove probe (if attached) -> NULL
        queue/sink -> remove them from the pipeline -> unlink (never
        release) the demux's request pad. Safe to call for a camera with no
        Tier 2 branch (nothing to do).

        The demux request pad is deliberately kept (see ``_demux_pads``):
        the original implementation called
        ``demux.release_request_pad(branch.demux_pad)`` here, which was
        confirmed on real hardware to be unsafe while the pipeline is
        PLAYING -- releasing an nvstreamdemux request pad at runtime is
        exactly the operation NVIDIA's own reference deepstream-app and
        multiple NVIDIA Developer Forum threads warn never to do
        dynamically; only linking/unlinking is supported. This method now
        only unlinks."""
        branch = self._branches.pop(camera_id, None)
        if branch is None:
            return

        probe_id = self._probe_ids.pop(camera_id, None)
        if probe_id is not None:
            queue_src_pad = branch.queue.get_static_pad("src")
            queue_src_pad.remove_probe(probe_id)

        Gst = _import_gst()
        queue_sink_pad = branch.queue.get_static_pad("sink")
        if branch.demux_pad.is_linked():
            branch.demux_pad.unlink(queue_sink_pad)
        for element in (branch.queue, branch.sink):
            element.set_state(Gst.State.NULL)
        for element in (branch.queue, branch.sink):
            self._gst_pipeline.remove(element)

    def _find_pad(self, camera_id: uuid.UUID) -> Any | None:
        branch = self._branches.get(camera_id)
        if branch is None:
            return None
        return branch.queue.get_static_pad("src")

    def _deliver(self, consumer: Tier2FrameConsumer, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        consumer.on_annotated_frame(camera_id, gst_buffer)
