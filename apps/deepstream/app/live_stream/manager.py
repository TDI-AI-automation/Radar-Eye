"""LiveStreamManager -- the single Live Monitoring subsystem boundary.

Mirrors ``visualization/manager.py``'s own "nothing outside this package
touches internal collaborators" rule: ``runtime.py`` only ever calls
``add_camera``/``remove_camera``/``start``/``stop``/``handle_offer`` here.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import LiveStreamSettings, VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.live_stream.branch import CameraWebRtcBranch
from apps.deepstream.app.live_stream.signaling_server import LiveStreamSignalingServer
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

logger = logging.getLogger(__name__)


class LiveStreamManager:
    def __init__(
        self,
        pipeline: Any,
        *,
        bridge: AsyncBridge,
        loop: asyncio.AbstractEventLoop,
        settings: LiveStreamSettings,
        visualization_settings: VisualizationSettings,
        track_annotations: TrackAnnotationRegistry,
        instrumentation: PerformanceInstrumentation | None,
        streammux_width: int,
        streammux_height: int,
    ) -> None:
        self._pipeline = pipeline
        self._bridge = bridge
        self._loop = loop
        self._settings = settings
        self._visualization_settings = visualization_settings
        self._track_annotations = track_annotations
        self._instrumentation = instrumentation
        self._width = streammux_width
        self._height = streammux_height
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

        sgie_tee = self._pipeline.sgie_tee()
        if sgie_tee is None:
            logger.warning(
                "Live Monitoring: no SGIE tee available (build() not called with "
                "live_stream_enabled=True?) -- camera %s will have no video branch",
                camera_id,
            )
            return

        branch = CameraWebRtcBranch(
            self._pipeline.gst_pipeline(),
            sgie_tee,
            camera_id,
            camera_name,
            streammux_width=self._width,
            streammux_height=self._height,
            live_settings=self._settings,
            visualization_settings=self._visualization_settings,
            track_annotations=self._track_annotations,
            instrumentation=self._instrumentation,
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

        self._branches[camera_id] = branch

    async def remove_camera(self, camera_id: uuid.UUID) -> None:
        branch = self._branches.pop(camera_id, None)
        if branch is None:
            return
        try:
            await branch.teardown()
        except Exception:
            logger.exception(
                "Live Monitoring failed to tear down WebRTC branch for camera %s", camera_id
            )

    async def handle_offer(self, camera_id: uuid.UUID, sdp_offer_text: str) -> str:
        branch = self._branches.get(camera_id)
        if branch is None:
            raise KeyError(camera_id)
        return await branch.handle_offer(sdp_offer_text)
