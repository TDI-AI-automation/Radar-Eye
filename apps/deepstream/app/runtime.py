"""DeepStream runtime composition and lifecycle (Phase 0 + Phase 1 + Phase 2).

Wires together everything RM-11 owns: the camera roster (DB), the GStreamer
pipeline (streammux/PGIE/tracker/SGIE as of Phase 2), the GLib<->asyncio
bridge, the Runtime Adapter, the heartbeat scheduler, performance
instrumentation (Phase 1), and the ThreatEngineRuntimeAdapter orchestration
layer (Phase 2). Per the RM-11 design review's Decision A, this all lives
in one OS process sharing one asyncio loop -- ``DeepStreamRuntime`` does not
start its own competing loop; callers (see ``main.py``) pass in the loop
they are already running.

Every processed ``FrameObservation`` reaches two independent consumers,
scheduled separately onto the asyncio loop: ``RuntimeAdapter`` (Phase 0/1 --
instrumentation and logging) and ``ThreatEngineRuntimeAdapter`` (Phase 2 --
threat assessment orchestration). Keeping them as separate scheduled calls,
rather than nesting one inside the other, preserves the architecture the
Phase 2 design review approved: DeepStream Runtime -> Runtime Adapter ->
FrameObservation -> ThreatEngineRuntimeAdapter -> application services.

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
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import DeepStreamSettings, ModelsSettings
from apps.deepstream.app.health.heartbeat import FrameCounter, HeartbeatScheduler
from apps.deepstream.app.ingestion.camera_registry import CameraRegistry
from apps.deepstream.app.ingestion.reconnect import ReconnectPolicy
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.instrumentation import PerformanceInstrumentation, PerformanceSnapshot
from apps.deepstream.app.pipeline.builder import DeepStreamPipeline
from apps.deepstream.app.runtime_adapter import RuntimeAdapter
from apps.deepstream.app.threat_runtime_adapter import ThreatEngineRuntimeAdapter
from services.incident_service.alarm import AlarmService
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
        models: ModelsSettings,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        encryption: Any,
    ) -> None:
        self._loop = loop
        self._settings = settings
        self._models = models
        self._session_factory = session_factory
        self._bus = bus
        self._encryption = encryption

        # RM-11.SIV Decision C: placeholder status now comes from
        # configs/models.yaml (pgie.enabled/sgie.enabled), not
        # DeepStreamSettings -- computed here rather than read off
        # self._pipeline.pgie_is_placeholder because that attribute is only
        # set once build() runs, later than this constructor.
        self._instrumentation = PerformanceInstrumentation(
            pgie_is_placeholder=not models.pgie.enabled
        )
        self._runtime_adapter = RuntimeAdapter(bus, instrumentation=self._instrumentation)

        # Phase 2: AlarmService is a long-lived singleton (its in-memory
        # _records state must persist across escalation calls, unlike
        # IncidentService/CalibrationService which are constructed fresh
        # per short-lived session -- see threat_runtime_adapter.py).
        self._alarm_service = AlarmService(bus=bus)
        self._threat_runtime_adapter = ThreatEngineRuntimeAdapter(
            session_factory=session_factory, bus=bus, alarm_service=self._alarm_service
        )

        self._frame_counter = FrameCounter()
        self._bridge = AsyncBridge(loop)
        self._pipeline = DeepStreamPipeline(
            settings,
            models,
            frame_counter=self._frame_counter,
            on_bus_message=self._on_bus_message,
            on_inference_buffer=self._on_inference_buffer,
        )
        self._policies: dict[uuid.UUID, ReconnectPolicy] = {}
        self._heartbeat: HeartbeatScheduler | None = None
        self._health_collector: Any | None = None
        self._metrics_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async with self._session_factory() as session:
            registry = CameraRegistry(session, self._encryption)
            camera_sources = await registry.load_camera_sources()

        self._instrumentation.mark_pipeline_build_start()
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

        self._metrics_task = asyncio.get_event_loop().create_task(self._sample_metrics_forever())

    def set_health_collector(self, health_collector: Any) -> None:
        """Injects the shared apps.api ``HealthCollector`` instance (RM-11
        design review, Decision A: single process, shared in-process state).
        Kept as an explicit setter rather than a constructor arg so
        DeepStreamRuntime doesn't hard-import apps.api.app.main at module
        load time."""
        self._health_collector = health_collector

    def get_metrics_snapshot(self) -> PerformanceSnapshot:
        """RM-11 Phase 1 approval: 'collect and expose' performance
        metrics. Exposed here as a plain getter (also periodically logged,
        see ``_sample_metrics_forever``) -- a REST/WebSocket surface is
        RM-12's job, out of RM-11 Phase 1's scope."""
        return self._instrumentation.snapshot()

    async def _sample_metrics_forever(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._settings.metrics_sample_interval_seconds)
                self._instrumentation.sample_system_metrics()
                logger.info("DeepStream performance snapshot: %s", self.get_metrics_snapshot())
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._metrics_task is not None:
            self._metrics_task.cancel()
            self._metrics_task = None
        if self._heartbeat is not None:
            self._heartbeat.stop()
        self._pipeline.stop()
        self._bridge.stop()
        await self._alarm_service.stop()  # ADR-012/026 fail-safe shutdown

    def _on_inference_buffer(
        self,
        gst_buffer: Any,
        camera_id_for_pad_index: dict[int, uuid.UUID],
        ingress_monotonic_seconds: float,
        ingress_wallclock: datetime,
    ) -> None:
        """Runs on a GStreamer streaming thread (the SGIE src pad probe).
        Extraction happens synchronously, still inside RuntimeAdapter
        (ADR-027) -- see extract_frame_observations's docstring for why
        this cannot be deferred onto the asyncio loop. Only the resulting
        plain FrameObservation values cross the bridge, to two independent
        consumers (see the module docstring).

        ``metadata_monotonic_seconds`` is captured immediately after
        extraction returns (still synchronous, same thread) -- close enough
        to "when metadata became available" for instrumentation purposes.
        """
        observations = self._runtime_adapter.extract_frame_observations(
            gst_buffer,
            camera_id_for_pad_index=camera_id_for_pad_index,
            ingress_timestamp=ingress_wallclock,
        )
        metadata_monotonic_seconds = time.monotonic()
        for observation in observations:
            self._bridge.schedule(
                self._runtime_adapter.on_frame_observation(
                    observation,
                    ingress_monotonic_seconds=ingress_monotonic_seconds,
                    metadata_monotonic_seconds=metadata_monotonic_seconds,
                )
            )
            self._bridge.schedule(self._threat_runtime_adapter.on_frame_observation(observation))

    def _on_bus_message(self, message: Any) -> None:
        """Runs on the GLib main-loop thread (bus signal watch dispatch)."""
        if self._pipeline.is_pipeline_state_changed_to_playing(message):
            self._instrumentation.mark_pipeline_playing()
            return

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
