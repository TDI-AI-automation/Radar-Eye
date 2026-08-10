"""Bitstream (original, pre-decode H.264) publisher -- Live Streaming
architecture reset.

Attaches to the per-camera bitstream tee's already-existing stub branch
(``pipeline/frame_distributor.py``'s ``attach_bitstream_branch``) -- no
pipeline topology change of its own. That branch (``bitstream-queue`` ->
``bitstream-sink``) exists for every camera the moment its source bin is
built, and stays exactly as bounded/leaky as that module left it whether
or not anything is attached, so the bitstream keeps flowing regardless
of decode/AI state or of whether any publisher is currently registered
-- ``BitstreamPublisher`` only ever adds/removes a read-only probe on
the queue's src pad, downstream of that queue's own backpressure
isolation.

Deliberately not named ``Tier0Publisher``: Tier 1/Tier 2 (``tier1.py``/
``tier2.py``) distribute *decoded* frames; this distributes the camera's
still-encoded bitstream, upstream of any decode at all -- a structurally
different resource, per ``docs/DEEPSTREAM_PIPELINE_SPEC.md``'s "every
media representation exists exactly once" principle. Encoded H.264 has
exactly one producer (``h264parse``, shared via the bitstream tee); this
publisher is one of potentially several consumers of that one producer.

Future consumers: Recording, Archive, Cloud relay. Not implemented here.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.deepstream.app.media_publisher.base import GstBridge, _TieredPublisher
from apps.deepstream.app.media_publisher.interfaces import BitstreamFrameConsumer
from apps.deepstream.app.pipeline.frame_distributor import bitstream_queue_element_name


class PipelineHandle(Protocol):
    """The one thing BitstreamPublisher needs from ``DeepStreamPipeline`` --
    matches ``media_publisher/tier1.py``'s own narrow-Protocol pattern
    rather than a concrete-class dependency."""

    def bin_for(self, camera_id: uuid.UUID) -> Any | None: ...


class BitstreamPublisher(_TieredPublisher[BitstreamFrameConsumer]):
    def __init__(self, pipeline: PipelineHandle, bridge: GstBridge) -> None:
        super().__init__(bridge)
        self._pipeline = pipeline

    def _find_pad(self, camera_id: uuid.UUID) -> Any | None:
        bin_ = self._pipeline.bin_for(camera_id)
        if bin_ is None:
            return None
        queue = bin_.get_by_name(bitstream_queue_element_name(camera_id))
        if queue is None:
            return None
        return queue.get_static_pad("src")

    def _deliver(
        self, consumer: BitstreamFrameConsumer, camera_id: uuid.UUID, gst_buffer: Any
    ) -> None:
        consumer.on_encoded_frame(camera_id, gst_buffer)
