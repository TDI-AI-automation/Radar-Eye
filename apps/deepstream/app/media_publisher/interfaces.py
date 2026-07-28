"""Frame consumer contracts -- RM-12 Camera Runtime Step 7.

``Tier1FrameConsumer`` was originally named (and left deliberately unwired)
in ``pipeline/frame_distributor.py`` (Step 2); relocated here now that this
is the milestone that actually attaches it. ``Tier2FrameConsumer`` is its
symmetric counterpart for annotated media.

Both are plain, synchronous callbacks -- invoked directly from a GStreamer
pad probe on whichever streaming thread owns that buffer, exactly like
``ai_runtime.detection.RuntimeAdapter.extract_frame_observations`` and the
pipeline's other buffer probes. A real consumer that needs to do
asyncio-side work must hand off itself (e.g. via ``AsyncBridge.schedule``)
-- these callbacks must never block waiting on the asyncio loop.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class Tier1FrameConsumer(Protocol):
    """Receives raw, pre-AI frames -- RM-12 Two-Tier Pattern Part A: "any
    capability that only needs the picture attaches to Tier 1." Delivered
    regardless of a camera's AI-enabled state (Tier 1 is upstream of the
    valve) -- see ``media_publisher/tier1.py``."""

    def on_raw_frame(self, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        """Called with each raw decoded frame's ``Gst.Buffer``."""
        ...


class Tier2FrameConsumer(Protocol):
    """Receives annotated frames -- available only while a camera is
    AI-enabled (Tier 2 sits downstream of PGIE/Tracker/SGIE, which the
    valve gates -- see ``media_publisher/tier2.py``)."""

    def on_annotated_frame(self, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        """Called with each post-SGIE frame's ``Gst.Buffer``."""
        ...
