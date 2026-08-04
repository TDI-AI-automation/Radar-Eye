"""IngestionRuntime -- Camera Ingestion Service's top-level orchestrator.

Owns: the shared ``Gst.Pipeline`` (one process, N independent per-camera
bins -- no shared muxer of any kind; unlike DeepStream, nothing here
ever needs to batch cameras together), the camera roster poll loop (no
AI-eligibility concept -- every registered camera with a stream profile
is always ingested), reconnect policy per camera, and publishing each
camera's encoded output via the Media Distribution Interface
(``shared.media_transport``).

Observed-State-accuracy discipline reused from the DeepStream-side
lesson this session already root-caused and fixed: a camera is marked
RECONNECTING (not CONNECTED) the moment its source bin is built --
add_source() succeeding only means the GStreamer elements were
constructed and linked, not that rtspsrc has actually finished its RTSP
handshake with the camera. Only a one-shot first-buffer probe (the
earliest point that actually confirms the RTSP stream is delivering
data) promotes it to CONNECTED.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from apps.api.app.repositories.media import (
    CameraMediaEndpointRepository,
    CameraSubsystemHealthRepository,
)
from apps.ingestion.app.camera_registry import CameraRegistry, CameraSource
from apps.ingestion.app.config import IngestionSettings
from apps.ingestion.app.source import IngestedSource
from shared.gst_bridge import AsyncBridge
from shared.media_transport.rtsp import RtspMediaPublisher
from shared.reconnect import ReconnectPolicy

logger = logging.getLogger(__name__)

_SUBSYSTEM = "ingestion"


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    Gst.init(None)
    return Gst


class IngestionRuntime:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        settings: IngestionSettings,
        session_factory: Any,
    ) -> None:
        self._loop = loop
        self._settings = settings
        self._session_factory = session_factory

        self._bridge = AsyncBridge(loop)
        self._pipeline: Any = None
        self._publisher: RtspMediaPublisher | None = None

        self._sources: dict[uuid.UUID, IngestedSource] = {}
        self._policies: dict[uuid.UUID, ReconnectPolicy] = {}
        self._sync_task: asyncio.Task[None] | None = None
        self._running = False

    # -- Startup / shutdown ------------------------------------------------

    async def start(self) -> None:
        Gst = _import_gst()
        self._pipeline = Gst.Pipeline.new("radar-eye-ingestion")
        self._bridge.start()

        self._publisher = RtspMediaPublisher(
            self._pipeline,
            host=self._settings.publish_host,
            rtsp_port=self._settings.publish_rtsp_port,
            udp_port_range_start=self._settings.publish_udp_port_range_start,
            subsystem=_SUBSYSTEM,
        )
        await asyncio.wrap_future(self._bridge.schedule_on_mainloop(self._publisher.start))

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        await asyncio.wrap_future(
            self._bridge.schedule_on_mainloop(lambda: self._pipeline.set_state(Gst.State.PLAYING))
        )

        self._running = True
        await self._synchronize()
        self._sync_task = self._loop.create_task(self._synchronize_forever())
        logger.info(
            "Camera Ingestion publishing on rtsp://%s:%s/<camera_id>",
            self._settings.publish_host,
            self._settings.publish_rtsp_port,
        )

    async def stop(self) -> None:
        self._running = False
        if self._sync_task is not None:
            self._sync_task.cancel()
            self._sync_task = None
        for camera_id in list(self._sources):
            await self._remove_camera(camera_id)
        if self._publisher is not None:
            await asyncio.wrap_future(self._bridge.schedule_on_mainloop(self._publisher.stop))
        if self._pipeline is not None:
            Gst = _import_gst()
            await asyncio.wrap_future(
                self._bridge.schedule_on_mainloop(lambda: self._pipeline.set_state(Gst.State.NULL))
            )
        self._bridge.stop()

    # -- Camera roster convergence ------------------------------------------

    async def _synchronize_forever(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._settings.desired_state_poll_interval_seconds)
                try:
                    await self._synchronize()
                except Exception:
                    logger.exception("Camera Ingestion synchronize() failed")
        except asyncio.CancelledError:
            pass

    async def _synchronize(self) -> None:
        async with self._session_factory() as session:
            from apps.api.app.config import get_settings as get_api_settings  # noqa: PLC0415
            from apps.api.app.security.encryption import (  # noqa: PLC0415
                get_credential_encryption_provider,
            )

            registry = CameraRegistry(
                session, get_credential_encryption_provider(get_api_settings())
            )
            desired = await registry.load_camera_sources()

        desired_by_id = {source.camera_id: source for source in desired}

        for camera_id in list(self._sources):
            if camera_id not in desired_by_id:
                await self._remove_camera(camera_id)

        for camera_id, source in desired_by_id.items():
            if camera_id not in self._sources:
                await self._add_camera(source)

    async def _add_camera(self, source: CameraSource) -> None:
        ingested = IngestedSource(camera=source)
        self._sources[source.camera_id] = ingested
        self._policies[source.camera_id] = ReconnectPolicy(
            initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
            max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
            multiplier=self._settings.reconnect_backoff_multiplier,
        )
        await self._build_and_publish(ingested)
        await self._set_health(source.camera_id, status="RECONNECTING", detail=None)

    async def _build_and_publish(self, ingested: IngestedSource) -> None:
        def _build_on_mainloop() -> Any:
            bin_ = ingested.build(latency_ms=self._settings.rtsp_default_latency_ms)
            self._pipeline.add(bin_)
            bin_.sync_state_with_parent()
            self._attach_first_buffer_probe(ingested.camera_id, bin_)
            assert self._publisher is not None
            return self._publisher.publish(ingested.camera_id, bin_.get_static_pad("src"))

        endpoint = await asyncio.wrap_future(self._bridge.schedule_on_mainloop(_build_on_mainloop))
        async with self._session_factory() as session:
            await CameraMediaEndpointRepository(session).set_endpoint(
                ingested.camera_id,
                _SUBSYSTEM,
                transport=endpoint.transport,
                address=endpoint.address,
            )
            await session.commit()

    def _attach_first_buffer_probe(self, camera_id: uuid.UUID, bin_: Any) -> None:
        """One-shot: promotes this camera to CONNECTED the moment a real
        buffer is observed at the bin's own ghost src pad -- the
        earliest point that confirms the RTSP stream is actually
        delivering data, as opposed to the bin merely having been built
        and linked (see module docstring)."""
        Gst = _import_gst()
        pad = bin_.get_static_pad("src")
        probe_id_holder: list[int] = []

        def _on_first_buffer(_pad: Any, _info: Any) -> Any:
            if probe_id_holder:
                pad.remove_probe(probe_id_holder[0])
            self._bridge.schedule(self._on_first_buffer(camera_id))
            return Gst.PadProbeReturn.OK

        probe_id_holder.append(pad.add_probe(Gst.PadProbeType.BUFFER, _on_first_buffer))

    async def _on_first_buffer(self, camera_id: uuid.UUID) -> None:
        policy = self._policies.get(camera_id)
        if policy is not None:
            policy.reset()
        await self._set_health(camera_id, status="CONNECTED", detail=None)

    async def _remove_camera(self, camera_id: uuid.UUID) -> None:
        ingested = self._sources.pop(camera_id, None)
        self._policies.pop(camera_id, None)
        if ingested is None:
            return

        def _teardown_on_mainloop() -> None:
            Gst = _import_gst()
            assert self._publisher is not None
            self._publisher.unpublish(camera_id)
            if ingested.bin is not None:
                ingested.bin.set_state(Gst.State.NULL)
                self._pipeline.remove(ingested.bin)

        await asyncio.wrap_future(self._bridge.schedule_on_mainloop(_teardown_on_mainloop))
        async with self._session_factory() as session:
            await CameraMediaEndpointRepository(session).delete_endpoint(camera_id, _SUBSYSTEM)
            await session.commit()

    # -- Failure handling ----------------------------------------------------

    def _on_bus_message(self, _bus: Any, message: Any) -> None:
        """Runs on the GLib main-loop thread."""
        source = self._source_for_message(message)
        if source is None:
            return
        Gst = _import_gst()
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            reason = f"{err} -- {debug}"
        else:
            reason = "end of stream"
        logger.warning("Camera %s ingestion failure: %s", source.camera_id, reason)
        self._bridge.schedule(self._handle_failure(source.camera_id, reason))

    def _source_for_message(self, message: Any) -> IngestedSource | None:
        for source in self._sources.values():
            if source.is_failure_message(message):
                return source
        return None

    async def _handle_failure(self, camera_id: uuid.UUID, reason: str) -> None:
        ingested = self._sources.get(camera_id)
        if ingested is None:
            return
        await self._set_health(camera_id, status="DISCONNECTED", detail=reason)

        def _teardown_on_mainloop() -> None:
            Gst = _import_gst()
            assert self._publisher is not None
            self._publisher.unpublish(camera_id)
            if ingested.bin is not None:
                ingested.bin.set_state(Gst.State.NULL)
                self._pipeline.remove(ingested.bin)
                ingested.bin = None

        await asyncio.wrap_future(self._bridge.schedule_on_mainloop(_teardown_on_mainloop))

        policy = self._policies.setdefault(
            camera_id,
            ReconnectPolicy(
                initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
                max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
                multiplier=self._settings.reconnect_backoff_multiplier,
            ),
        )
        delay = policy.next_delay_seconds()
        logger.info("Scheduling ingestion reconnect for camera %s in %.1fs", camera_id, delay)
        await asyncio.sleep(delay)
        if camera_id not in self._sources or not self._running:
            return  # camera was deleted (or we're shutting down) while waiting
        await self._set_health(camera_id, status="RECONNECTING", detail=None)
        await self._build_and_publish(ingested)

    async def _set_health(self, camera_id: uuid.UUID, *, status: str, detail: str | None) -> None:
        async with self._session_factory() as session:
            await CameraSubsystemHealthRepository(session).set_health(
                camera_id, _SUBSYSTEM, status=status, detail=detail
            )
            await session.commit()
