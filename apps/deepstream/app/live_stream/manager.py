"""LiveStreamManager -- the single Live Monitoring subsystem boundary.

Mirrors ``visualization/manager.py``'s own "nothing outside this package
touches internal collaborators" rule: ``runtime.py`` only ever calls
``add_camera``/``remove_camera``/``start``/``stop``/``handle_offer``
here.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import LiveStreamSettings
from apps.deepstream.app.live_stream.branch import CameraWebRtcBranch
from apps.deepstream.app.live_stream.consumer import BitstreamAppsrcBridge
from apps.deepstream.app.live_stream.signaling_server import LiveStreamSignalingServer
from apps.deepstream.app.media_publisher.bitstream import BitstreamPublisher

logger = logging.getLogger(__name__)


class LiveStreamManager:
    def __init__(
        self,
        pipeline: Any,
        *,
        bitstream_publisher: BitstreamPublisher,
        bridge: AsyncBridge,
        loop: asyncio.AbstractEventLoop,
        settings: LiveStreamSettings,
    ) -> None:
        self._pipeline = pipeline
        self._bitstream_publisher = bitstream_publisher
        self._bridge = bridge
        self._loop = loop
        self._settings = settings
        self._appsrc_bridge = BitstreamAppsrcBridge()
        self._branches: dict[uuid.UUID, CameraWebRtcBranch] = {}
        self._signaling_server: LiveStreamSignalingServer | None = None

    async def start(self) -> None:
        if not self._settings.enabled:
            return
        self._signaling_server = LiveStreamSignalingServer(
            self, host=self._settings.host, port=self._settings.port
        )
        await self._signaling_server.start()
        logger.info(
            "Live Monitoring signaling server listening on %s:%s",
            self._settings.host,
            self._settings.port,
        )

    async def stop(self) -> None:
        if self._signaling_server is not None:
            await self._signaling_server.stop()
            self._signaling_server = None
        for camera_id in list(self._branches):
            await self.remove_camera(camera_id)

    async def add_camera(self, camera_id: uuid.UUID, camera_name: str) -> None:
        """Idempotent -- a camera reconnecting (same camera_id) is a
        no-op if its branch already exists, matching every other
        per-camera subsystem's (Visualization, Tier 2) established
        convention."""
        if not self._settings.enabled or camera_id in self._branches:
            return

        branch = CameraWebRtcBranch(
            self._pipeline.gst_pipeline(),
            camera_id,
            camera_name,
            live_settings=self._settings,
            appsrc_bridge=self._appsrc_bridge,
            bridge=self._bridge,
            loop=self._loop,
        )
        try:
            future = self._bridge.schedule_on_mainloop(branch.build)
            await asyncio.wrap_future(future)
        except Exception:  # noqa: BLE001 -- must never take the camera source down with it
            logger.exception(
                "Live Monitoring failed to build WebRTC branch for camera %s -- "
                "continuing without it (connectivity/AI are unaffected)",
                camera_id,
            )
            return

        self._bitstream_publisher.register(camera_id, self._appsrc_bridge)
        self._branches[camera_id] = branch
        # Not attached yet -- see handle_offer(). Real bitstream buffers
        # must not reach webrtcbin's sink pad before the first offer/answer
        # exchange completes: once they do, rtph264pay's payload type (a
        # concrete, fixed number) becomes part of the pad's received caps,
        # and GStreamer's compatible-transceiver search compares that fixed
        # number against the offer's own payload type number(s) -- which a
        # browser picks independently and will essentially never guess to
        # be the same number. Before any data has flowed, webrtcbin instead
        # queries upstream capability caps, where rtph264pay's pad template
        # advertises the whole dynamic range (payload=[96,127]), which
        # intersects successfully against whatever number the browser chose.

    async def remove_camera(self, camera_id: uuid.UUID) -> None:
        branch = self._branches.pop(camera_id, None)
        if branch is None:
            return
        await self._bitstream_publisher.detach(camera_id)
        self._bitstream_publisher.unregister(camera_id, self._appsrc_bridge)
        try:
            future = self._bridge.schedule_on_mainloop(branch.teardown)
            await asyncio.wrap_future(future)
        except Exception:
            logger.exception(
                "Live Monitoring failed to tear down WebRTC branch for camera %s", camera_id
            )

    async def handle_offer(self, camera_id: uuid.UUID, sdp_offer_text: str) -> str:
        branch = self._branches.get(camera_id)
        if branch is None:
            raise KeyError(camera_id)
        answer = await branch.handle_offer(sdp_offer_text)
        # Only now (negotiation already complete) is it safe to let real
        # bitstream buffers start flowing -- see add_camera()'s comment.
        # Idempotent: a second/reconnecting browser's offer finds the
        # publisher already attached and this is a no-op.
        await self._bitstream_publisher.attach(camera_id)
        return answer
