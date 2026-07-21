"""DeepStream runtime composition and lifecycle (Phase 0).

Wires together everything RM-11 owns: the camera roster (DB), the GStreamer
pipeline, the GLib<->asyncio bridge, the Runtime Adapter, and the heartbeat
scheduler. Per the RM-11 design review's Decision A, this all lives in one
OS process sharing one asyncio loop -- ``DeepStreamRuntime`` does not start
its own competing loop; callers (see ``main.py``) pass in the loop they are
already running.

Reconnect orchestration lives here (not in ``ingestion/source.py``, which
only builds/tears down GStreamer elements): a bus ERROR/EOS message for a
camera's bin is detected on the GLib thread, backoff timing comes from that
camera's own ``ReconnectPolicy`` (INV-012 -- one camera's failure state
never touches another's), and the rebuild itself is scheduled back onto the
GLib thread via ``GLib.timeout_add_seconds`` (GStreamer element/pipeline
mutation is expected to happen on the thread running the main loop).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import DeepStreamSettings
from apps.deepstream.app.health.heartbeat import FrameCounter, HeartbeatScheduler
from apps.deepstream.app.ingestion.camera_registry import CameraRegistry
from apps.deepstream.app.ingestion.reconnect import ReconnectPolicy
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.pipeline.builder import DeepStreamPipeline
from apps.deepstream.app.runtime_adapter import RuntimeAdapter
from shared.events.bus import EventBus

logger = logging.getLogger(__name__)


def _import_glib() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("GLib", "2.0")
    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst  # noqa: PLC0415

    return GLib, Gst


class DeepStreamRuntime:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        settings: DeepStreamSettings,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        encryption: Any,
    ) -> None:
        self._loop = loop
        self._settings = settings
        self._session_factory = session_factory
        self._bus = bus
        self._encryption = encryption

        self._runtime_adapter = RuntimeAdapter(bus)
        self._frame_counter = FrameCounter()
        self._bridge = AsyncBridge(loop)
        self._pipeline = DeepStreamPipeline(
            settings, frame_counter=self._frame_counter, on_bus_message=self._on_bus_message
        )
        self._policies: dict[uuid.UUID, ReconnectPolicy] = {}
        self._heartbeat: HeartbeatScheduler | None = None
        self._health_collector: Any | None = None

    async def start(self) -> None:
        async with self._session_factory() as session:
            registry = CameraRegistry(session, self._encryption)
            camera_sources = await registry.load_camera_sources()

        self._pipeline.build()
        self._bridge.start()

        for camera_source in camera_sources:
            self._policies[camera_source.camera_id] = ReconnectPolicy(
                initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
                max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
                multiplier=self._settings.reconnect_backoff_multiplier,
            )
            self._pipeline.add_source(RtspSource(camera=camera_source))
            await self._runtime_adapter.on_camera_connected(camera_source.camera_id)

        self._pipeline.start()

        if self._health_collector is None:
            raise RuntimeError(
                "DeepStreamRuntime requires a HealthCollector -- call "
                "set_health_collector() before start()"
            )
        self._heartbeat = HeartbeatScheduler(
            health_collector=self._health_collector,
            frame_counter=self._frame_counter,
            camera_ids=[c.camera_id for c in camera_sources],
            status_provider=self._runtime_adapter.status_for,
            interval_seconds=self._settings.heartbeat_interval_seconds,
        )
        self._heartbeat.start()

    def set_health_collector(self, health_collector: Any) -> None:
        """Injects the shared apps.api ``HealthCollector`` instance (RM-11
        design review, Decision A: single process, shared in-process state).
        Kept as an explicit setter rather than a constructor arg so
        DeepStreamRuntime doesn't hard-import apps.api.app.main at module
        load time."""
        self._health_collector = health_collector

    async def stop(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.stop()
        self._pipeline.stop()
        self._bridge.stop()

    def _on_bus_message(self, message: Any) -> None:
        """Runs on the GLib main-loop thread (bus signal watch dispatch)."""
        source = self._pipeline.source_for_message(message)
        if source is None:
            return

        reason = self._describe_message(message)
        logger.warning("Camera %s failure: %s", source.camera_id, reason)
        self._bridge.schedule(
            self._runtime_adapter.on_camera_disconnected(source.camera_id, reason)
        )
        self._pipeline.remove_source(source.camera_id)
        self._schedule_reconnect(source)

    def _schedule_reconnect(self, source: RtspSource) -> None:
        GLib, _Gst = _import_glib()
        policy = self._policies[source.camera_id]
        delay = policy.next_delay_seconds()
        logger.info(
            "Scheduling reconnect for camera %s in %.1fs (attempt %d)",
            source.camera_id,
            delay,
            policy.attempt_count,
        )

        def _reconnect() -> bool:
            self._bridge.schedule(self._runtime_adapter.on_camera_reconnecting(source.camera_id))
            try:
                new_source = RtspSource(camera=source.camera)
                self._pipeline.add_source(new_source)
            except Exception:
                logger.exception("Reconnect failed for camera %s, will retry", source.camera_id)
                self._schedule_reconnect(source)
                return False
            policy.reset()
            self._bridge.schedule(self._runtime_adapter.on_camera_connected(source.camera_id))
            return False  # one-shot timeout

        GLib.timeout_add_seconds(int(max(delay, 1)), _reconnect)

    @staticmethod
    def _describe_message(message: Any) -> str:
        _GLib, Gst = _import_glib()
        try:
            if message.type == Gst.MessageType.ERROR:
                err, _debug = message.parse_error()
                return str(err)
            return "EOS"
        except Exception:  # noqa: BLE001 -- best-effort description only
            return "unknown pipeline failure"
