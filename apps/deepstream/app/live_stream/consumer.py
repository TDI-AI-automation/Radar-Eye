"""BitstreamAppsrcBridge -- the appsrc-feeding consumer Live Streaming
registers against Media Publisher's ``BitstreamPublisher`` (see
``apps/deepstream/app/live_stream/__init__.py``'s module docstring).

Delivered on a GStreamer streaming thread (``BitstreamFrameConsumer``'s
own documented constraint -- see ``media_publisher/interfaces.py``); must
never block, and must never let an exception escape (that thread is the
pipeline's own streaming thread, not something this consumer is allowed
to interrupt). Pushing into an ``appsrc`` is itself a cheap, thread-safe
GStreamer operation (``appsrc`` is explicitly designed to accept
``push-buffer`` from any thread) -- no hand-off through ``AsyncBridge``
is needed here, unlike a consumer that needs to reach asyncio-side code.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.deepstream.app.stage_logging import get_stage_logger

logger = logging.getLogger(__name__)
_live_stream_logger = get_stage_logger("live_stream")


class BitstreamAppsrcBridge:
    """Implements ``BitstreamFrameConsumer``. Structurally identical to
    ``Tier1AppsrcBridge`` above -- a separate class rather than a shared
    base because the two implement different consumer Protocols
    (``on_raw_frame`` vs ``on_encoded_frame``), not because the logic
    differs.

    The appsrc's caps are taken from the bitstream queue's own negotiated
    caps (the real camera's H.264 access units, as ``h264parse`` actually
    produced them -- profile/level/resolution never guessed or
    hardcoded), read once the first buffer is observed, same technique
    as ``Tier1AppsrcBridge``.
    """

    def __init__(self) -> None:
        self._appsrcs: dict[uuid.UUID, Any] = {}
        self._source_pads: dict[uuid.UUID, Any] = {}
        self._caps_set: set[uuid.UUID] = set()
        self._first_buffer_seen: set[uuid.UUID] = set()
        self._first_push_done: set[uuid.UUID] = set()

    def set_appsrc(self, camera_id: uuid.UUID, appsrc: Any, source_pad: Any) -> None:
        self._appsrcs[camera_id] = appsrc
        self._source_pads[camera_id] = source_pad

    def remove_appsrc(self, camera_id: uuid.UUID) -> None:
        self._appsrcs.pop(camera_id, None)
        self._source_pads.pop(camera_id, None)
        self._caps_set.discard(camera_id)
        self._first_buffer_seen.discard(camera_id)
        self._first_push_done.discard(camera_id)

    def on_encoded_frame(self, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        appsrc = self._appsrcs.get(camera_id)
        if appsrc is None:
            return
        try:
            if camera_id not in self._first_buffer_seen:
                self._first_buffer_seen.add(camera_id)
                _live_stream_logger.info(
                    "Bitstream received: first encoded access unit for camera %s "
                    "(size=%d bytes) -- transport path is live",
                    camera_id,
                    gst_buffer.get_size(),
                )
            else:
                _live_stream_logger.debug(
                    "Bitstream received: camera %s (size=%d bytes)",
                    camera_id,
                    gst_buffer.get_size(),
                )

            if camera_id not in self._caps_set:
                source_pad = self._source_pads.get(camera_id)
                caps = source_pad.get_current_caps() if source_pad is not None else None
                if caps is not None:
                    appsrc.set_property("caps", caps)
                    self._caps_set.add(camera_id)
                else:
                    # Not yet negotiated -- skip this access unit rather
                    # than push into an appsrc with no caps; the next one
                    # (moments later) will almost certainly have them.
                    return
            appsrc.emit("push-buffer", gst_buffer)
            if camera_id not in self._first_push_done:
                self._first_push_done.add(camera_id)
                _live_stream_logger.info(
                    "AppSrc push: first encoded access unit pushed into WebRTC "
                    "appsrc for camera %s",
                    camera_id,
                )
            else:
                _live_stream_logger.debug("AppSrc push: camera %s", camera_id)
        except Exception:
            logger.exception(
                "Failed to push bitstream access unit into WebRTC appsrc for camera %s",
                camera_id,
            )
