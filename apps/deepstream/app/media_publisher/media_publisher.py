"""Media Publisher facade -- RM-12 Camera Runtime Step 7.

Thin composition object: owns one ``Tier1Publisher``, one
``Tier2Publisher``, and one ``BitstreamPublisher``, and provides the one
unified ``shutdown()`` a caller (``runtime.py``, or a hardware validation
script) needs -- everything else is used directly on
``.tier1``/``.tier2``/``.bitstream``, since these are independent
publishers with no shared behavior beyond the lifecycle machinery already
factored into ``_TieredPublisher``.
"""

from __future__ import annotations

from apps.deepstream.app.media_publisher.base import GstBridge
from apps.deepstream.app.media_publisher.bitstream import BitstreamPublisher
from apps.deepstream.app.media_publisher.tier1 import PipelineHandle, Tier1Publisher
from apps.deepstream.app.media_publisher.tier2 import Tier2Publisher


class MediaPublisher:
    def __init__(self, pipeline: PipelineHandle, bridge: GstBridge) -> None:
        self.tier1 = Tier1Publisher(pipeline, bridge)
        self.tier2 = Tier2Publisher(bridge)
        self.bitstream = BitstreamPublisher(pipeline, bridge)

    async def shutdown(self) -> None:
        """Detaches every attached camera on both tiers and the bitstream
        publisher. Does not touch Tier 2's per-camera branches themselves
        (those are torn down by ``Tier2Publisher.on_camera_removed()``,
        called from ``DeepStreamPipeline.remove_source()`` -- a
        pipeline-topology concern, not a publisher-shutdown concern)."""
        await self.tier1.shutdown()
        await self.tier2.shutdown()
        await self.bitstream.shutdown()
