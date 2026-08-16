"""Tier 1 (raw media) publisher -- RM-12 Camera Runtime Step 7.

Attaches to the per-camera Tier 1 tee's already-existing raw branch (Step
2, ``pipeline/frame_distributor.py``) -- no pipeline topology change of its
own. That branch (``tier1-raw-queue`` -> ``tier1-raw-sink``) exists for
every camera the moment its source bin is built, and stays exactly as
bounded/leaky as Step 2 left it whether or not anything is attached, so
Tier 1 keeps flowing regardless of AI state or of whether any publisher is
currently registered -- ``Tier1Publisher`` only ever adds/removes a
read-only probe on the queue's src pad, downstream of that queue's own
backpressure isolation.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.deepstream.app.media_publisher.base import GstBridge, _TieredPublisher
from apps.deepstream.app.media_publisher.interfaces import Tier1FrameConsumer
from apps.deepstream.app.pipeline.frame_distributor import tier1_raw_queue_element_name


class PipelineHandle(Protocol):
    """The one thing Tier1Publisher needs from ``DeepStreamPipeline`` --
    matches ``runtime_supervisor.PipelineHandle``/
    ``synchronization.SynchronizablePipeline``'s narrow-Protocol pattern
    rather than a concrete-class dependency."""

    def bin_for(self, camera_id: uuid.UUID) -> Any | None: ...


class Tier1Publisher(_TieredPublisher[Tier1FrameConsumer]):
    def __init__(self, pipeline: PipelineHandle, bridge: GstBridge) -> None:
        super().__init__(bridge)
        self._pipeline = pipeline

    def _find_pad(self, camera_id: uuid.UUID) -> Any | None:
        bin_ = self._pipeline.bin_for(camera_id)
        if bin_ is None:
            return None
        queue = bin_.get_by_name(tier1_raw_queue_element_name(camera_id))
        if queue is None:
            return None
        return queue.get_static_pad("src")

    def _deliver(self, consumer: Tier1FrameConsumer, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        consumer.on_raw_frame(camera_id, gst_buffer)
