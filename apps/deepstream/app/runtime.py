"""DeepStream runtime composition and lifecycle -- AI Runtime (ADR-029).

Wires together everything AI Runtime owns: the camera roster (DB), the
GStreamer pipeline (streammux/PGIE/tracker/SGIE), the GLib<->asyncio bridge,
the Runtime Adapter, the heartbeat scheduler, and performance instrumentation.
This all lives in one OS process sharing one asyncio loop -- ``DeepStreamRuntime``
does not start its own competing loop; callers (see ``main.py``) pass in the
loop they are already running.

Every processed ``FrameObservation`` reaches exactly one consumer, scheduled
onto the asyncio loop: ``RuntimeAdapter`` (instrumentation, logging, and
publishing ``ObservationEvent`` -- AI Runtime's only outward product besides
AI Streaming). Per ADR-029, AI Runtime is a pure CV engine: it never calls
Calibration, Threat Engine, Incident Service, Alert Service, or Hardware
Action Service directly (that orchestration -- formerly
``ThreatEngineRuntimeAdapter``, RM-11 Phase 2 -- has been removed from this
process; see ADR-029 and ADR_INDEX.md). Downstream services consume
``ObservationEvent`` off the Event Bus instead.

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

from apps.deepstream.app.ai_runtime.detection import RuntimeAdapter
from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.config import (
    DeepStreamSettings,
    LiveStreamSettings,
    ModelsSettings,
    ValidationSettings,
    VisualizationSettings,
)
from apps.deepstream.app.desired_state import DesiredStateReader
from apps.deepstream.app.health.heartbeat import FrameCounter, HeartbeatScheduler
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.ingestion.reconnect import ReconnectPolicy
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.instrumentation import PerformanceInstrumentation, PerformanceSnapshot
from apps.deepstream.app.live_stream.manager import LiveStreamManager
from apps.deepstream.app.media_publisher.media_publisher import MediaPublisher
from apps.deepstream.app.pipeline.builder import DeepStreamPipeline
from apps.deepstream.app.pipeline_trace import PipelineTracer
from apps.deepstream.app.runtime_supervisor import ConcurrentEnableLimiter, RuntimeSupervisor
from apps.deepstream.app.stage_logging import get_audit_logger
from apps.deepstream.app.synchronization import DesiredStateSynchronizer
from apps.deepstream.app.telemetry import TelemetryCollector
from apps.deepstream.app.visualization.manager import VisualizationManager
from shared.events.bus import EventBus

logger = logging.getLogger(__name__)
_audit_logger = get_audit_logger()


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
        validation: ValidationSettings,
        visualization: VisualizationSettings,
        live_stream: LiveStreamSettings,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
    ) -> None:
        self._loop = loop
        self._settings = settings
        self._models = models
        self._session_factory = session_factory
        self._bus = bus

        # RM-11.SIV Unified Heartbeat: one registry, shared by every
        # component below and (read-only) by the watchdog/dashboard --
        # exposed as a public attribute (not self._heartbeat -- already
        # taken by the RM-09 HeartbeatScheduler below) so scripts/run_siv.py
        # can wire them up without reaching into private state.
        self.heartbeat_registry = HeartbeatRegistry()
        self._tracer = PipelineTracer(enabled=validation.frame_trace.enabled)

        self.visualization_manager = VisualizationManager(visualization)
        """RM-11.SIV visualization subsystem -- public (matching
        heartbeat_registry/instrumentation above) so scripts/run_siv.py's
        dashboard/watchdog can read .health() later without reaching into
        private state. Always constructed regardless of
        visualization.enabled -- see manager.py's own docstring for why."""

        # RM-11.SIV Decision C: placeholder status now comes from
        # configs/models.yaml (pgie.enabled/sgie.enabled), not
        # DeepStreamSettings -- computed here rather than read off
        # self._pipeline.pgie_is_placeholder because that attribute is only
        # set once build() runs, later than this constructor.
        self._instrumentation = PerformanceInstrumentation(
            pgie_is_placeholder=not models.pgie.enabled
        )
        self.instrumentation = self._instrumentation
        """Public alias -- RM-11.SIV's siv/watchdog.py and siv/dashboard.py
        (constructed externally by scripts/run_siv.py, never imported here
        -- see apps/deepstream/app/siv/__init__.py) need direct read access
        to call .snapshot() themselves, not just the periodic log line
        _sample_metrics_forever already produces."""
        self._runtime_adapter = RuntimeAdapter(
            bus,
            instrumentation=self._instrumentation,
            heartbeat=self.heartbeat_registry,
            tracer=self._tracer,
            session_factory=session_factory,
        )

        self._live_stream_settings = live_stream
        self._frame_counter = FrameCounter()
        self._bridge = AsyncBridge(loop)
        self._pipeline = DeepStreamPipeline(
            settings,
            models,
            frame_counter=self._frame_counter,
            on_bus_message=self._on_bus_message,
            on_inference_buffer=self._on_inference_buffer,
            heartbeat=self.heartbeat_registry,
            instrumentation=self._instrumentation,
            visualization_settings=visualization,
            visualization_manager=self.visualization_manager,
            media_publisher_enabled=True,
            live_stream_enabled=live_stream.enabled,
            on_source_added=self._on_live_stream_source_added,
            on_source_removed=self._on_source_removed,
            on_source_first_buffer=self._on_source_first_buffer,
        )

        # RM-12 Camera Runtime v1 (Steps 1-7): first production wiring of
        # the completed blueprint. Desired State Synchronization converges
        # the pipeline toward Camera Registry's Desired State (Step 4),
        # replacing the previous unconditional "load every registered
        # camera" behavior in start() below; Media Publisher owns Tier 1/
        # Tier 2 publisher lifecycle (Step 7); Telemetry observes all of
        # the above without ever influencing them (Step 5). Construction
        # order matters: MediaPublisher needs self._pipeline to already
        # exist (Tier1Publisher reads bin_for() lazily), but
        # DeepStreamPipeline needs a Tier2Publisher reference before
        # build() runs -- broken via set_tier2_publisher(), the same
        # "setter for a not-yet-available dependency" pattern already used
        # by set_health_collector() below. MediaPublisher is built before
        # RuntimeSupervisor -- unrelated to Live Monitoring, purely
        # because Tier2Publisher must exist before DeepStreamPipeline.build().
        self.media_publisher = MediaPublisher(self._pipeline, self._bridge)
        self._pipeline.set_tier2_publisher(self.media_publisher.tier2)
        self.live_stream_manager = LiveStreamManager(
            self._pipeline,
            bridge=self._bridge,
            settings=live_stream,
            visualization_settings=visualization,
            track_annotations=self.visualization_manager.track_annotations,
            instrumentation=self._instrumentation,
            streammux_width=settings.streammux_width,
            streammux_height=settings.streammux_height,
            session_factory=session_factory,
        )
        """Live Monitoring's permanent video delivery path -- see
        apps/deepstream/app/live_stream/__init__.py. AI-annotated-only
        (ADR-030): one input, the AI pipeline's own already-produced
        annotated output, tapped off the shared SGIE tee and encoded
        independently -- no raw passthrough, no runtime source switch.
        Delivered to the browser as HLS (ADR-031): DeepStream writes
        segments/playlist to disk and never mutates this branch for a
        browser connecting, disconnecting, or refreshing -- see
        ``live_stream/branch.py``. Reuses VisualizationManager's
        already-live TrackAnnotationRegistry -- no new overlay-rendering
        mechanism. Per ADR-029, nothing populates this registry from
        inside AI Runtime anymore (previously ThreatEngineRuntimeAdapter);
        it is a preserved interface, read as always-empty until a later
        phase feeds it again over the Event Bus."""
        self.runtime_supervisor = RuntimeSupervisor(
            self._pipeline,
            self._bridge,
            ConcurrentEnableLimiter(max_concurrent=settings.streammux_batch_size),
        )
        self._desired_state_reader = DesiredStateReader(session_factory)
        self.desired_state_synchronizer = DesiredStateSynchronizer(
            self._desired_state_reader,
            self._pipeline,
            self._bridge,
            self.runtime_supervisor,
            on_source_connected=self._on_source_added_pending_confirmation,
        )
        self.telemetry = TelemetryCollector(
            pipeline=self._pipeline,
            runtime_supervisor=self.runtime_supervisor,
            synchronizer=self.desired_state_synchronizer,
            bridge=self._bridge,
            instrumentation=self._instrumentation,
        )

        self._policies: dict[uuid.UUID, ReconnectPolicy] = {}
        self._heartbeat: HeartbeatScheduler | None = None
        self._health_collector: Any | None = None
        self._metrics_task: asyncio.Task[None] | None = None
        self._telemetry_task: asyncio.Task[None] | None = None
        self._desired_state_sync_task: asyncio.Task[None] | None = None
        self._desired_state_sync_running = False
        self._observed_state_flush_tasks: set[asyncio.Task[None]] = set()
        self._last_health_flush: dict[uuid.UUID, float] = {}
        """camera_id -> monotonic time of its last persisted fps/latency
        write. Throttles HeartbeatScheduler's on_health_snapshot hook
        (which fires every heartbeat tick) down to
        observed_state_flush_interval_seconds, per the Camera Connectivity
        migration's write-volume constraint -- high-frequency metrics must
        not be written every tick."""

    async def start(self) -> None:
        self._instrumentation.mark_pipeline_build_start()
        self._pipeline.build()
        self._bridge.start()
        await self.live_stream_manager.start()

        # RM-12 Camera Runtime v1: initial Desired State convergence
        # replaces the previous unconditional "add every registered camera"
        # loop -- every registered camera gets an active source (Lifecycle,
        # which used to gate this, has been removed entirely), and AI is
        # converged from ai_enabled alone.
        # desired_state_synchronizer's own on_source_connected hook (wired
        # above) already notifies RuntimeAdapter.on_camera_connected for
        # every source added by this call -- including these, the very
        # first ones -- so this loop only needs to pre-seed each one's
        # ReconnectPolicy, not connect them a second time.
        result = await self.desired_state_synchronizer.synchronize()
        logger.info("Initial Desired State synchronization: %s", result.actions_taken)

        active_camera_ids = list(self._pipeline.active_camera_ids())
        for camera_id in active_camera_ids:
            self._policies[camera_id] = ReconnectPolicy(
                initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
                max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
                multiplier=self._settings.reconnect_backoff_multiplier,
            )

        self._pipeline.start()

        if self._health_collector is None:
            raise RuntimeError(
                "DeepStreamRuntime requires a HealthCollector -- call "
                "set_health_collector() before start()"
            )
        self._heartbeat = HeartbeatScheduler(
            health_collector=self._health_collector,
            frame_counter=self._frame_counter,
            camera_ids=active_camera_ids,
            status_provider=self._runtime_adapter.status_for,
            interval_seconds=self._settings.heartbeat_interval_seconds,
            on_tick=lambda: self.heartbeat_registry.beat("heartbeat"),
            on_health_snapshot=self._on_health_snapshot,
        )
        self._heartbeat.start()

        self.telemetry.start()
        loop = asyncio.get_event_loop()
        self._metrics_task = loop.create_task(self._sample_metrics_forever())
        self._telemetry_task = loop.create_task(self._sample_telemetry_forever())
        self._desired_state_sync_task = loop.create_task(self._synchronize_desired_state_forever())

    def set_health_collector(self, health_collector: Any) -> None:
        """Injects the shared apps.api ``HealthCollector`` instance (RM-11
        design review, Decision A: single process, shared in-process state).
        Kept as an explicit setter rather than a constructor arg so
        DeepStreamRuntime doesn't hard-import apps.api.app.main at module
        load time."""
        self._health_collector = health_collector

    def _on_live_stream_source_added(self, camera_id: uuid.UUID, camera_name: str) -> None:
        """DeepStreamPipeline.add_source()'s on_source_added hook. Fires
        synchronously on the GLib thread, at the same call site
        VisualizationManager/Tier2Publisher already hook into --
        live_stream_manager.add_camera() is itself async (awaits
        Tier1Publisher.attach()), so it's scheduled onto the asyncio loop
        the same way every other GLib->asyncio hand-off in this module
        already is, rather than called directly here. Referencing
        self.live_stream_manager here (rather than at DeepStreamPipeline
        construction time, which happens before it exists) is safe --
        this hook is only ever invoked later, once add_source() actually
        runs, by which point construction has long finished."""
        self._bridge.schedule(self.live_stream_manager.add_camera(camera_id, camera_name))

    async def _on_source_added_pending_confirmation(self, camera_id: uuid.UUID) -> None:
        """DesiredStateSynchronizer's on_source_connected hook -- despite
        the name (kept for that module's own docstring/tests, which are
        about "a source this synchronizer just added", not about the
        specific status it produces), this no longer marks the camera
        CONNECTED. Observed-State-accuracy fix (found investigating a
        real "UI shows healthy/connected but the video is black"
        report): add_source() succeeding only means the GStreamer
        elements were constructed and linked -- it says nothing about
        whether rtspsrc has actually finished its RTSP handshake with
        the camera. Marking RECONNECTING here (reconnect=False -- this
        is a fresh add, not a recovery, so it must not bump
        reconnect_count) and leaving the promotion to CONNECTED to
        _on_source_first_buffer below means the UI now reflects reality:
        "trying to establish the stream" until a real buffer is actually
        observed, not the instant pipeline construction finishes."""
        await self._runtime_adapter.on_camera_reconnecting(camera_id, reconnect=False)

    def _on_source_first_buffer(self, camera_id: uuid.UUID) -> None:
        """DeepStreamPipeline's one-shot first-buffer probe (see
        _attach_first_buffer_probe) -- runs on a GStreamer streaming
        thread, so hand off to asyncio the same way every other
        non-asyncio-thread callback in this module already does. The
        one and only place a camera is ever promoted to CONNECTED --
        covers both the initial add (_on_source_added_pending_confirmation
        marks RECONNECTING first) and every reconnect (add_source() is
        the single choke point both paths funnel through, so a fresh
        one-shot probe is attached to the fresh bin either way)."""
        self._bridge.schedule(self._runtime_adapter.on_camera_connected(camera_id))

    def _on_source_removed(self, camera_id: uuid.UUID) -> None:
        """DeepStreamPipeline.remove_source()'s on_source_removed hook --
        the single, symmetric counterpart to every per-camera subsystem's
        own creation path (LiveStreamManager.add_camera,
        RuntimeSupervisor's lazy worker creation, RuntimeAdapter.
        on_camera_connected, this module's own ReconnectPolicy/health-
        flush bookkeeping). Covers every removal path uniformly (bus-
        message failure, reconnect, and deletion-driven removal via
        DesiredStateSynchronizer) since all of them funnel through
        remove_source().

        Root-cause fix (Operator Acceptance Testing ownership audit,
        2026-08-03, prompted by a suspected "deeper lifecycle/ownership
        problem" behind repeated delete/re-register regressions): a full
        audit of every dict[camera_id, ...] in this package found that
        only LiveStreamManager/MediaPublisher were ever wired into this
        hook -- RuntimeSupervisor's per-camera worker, RuntimeAdapter's
        status cache, and this module's own _policies/_last_health_flush
        entries were write-only, growing by one permanent entry per
        operator delete/re-register cycle for the life of the process.
        Confirmed via reproduction that this leak was NOT the cause of
        the originally reported 502/permanently-disconnected symptom
        (already fixed by the sink-to-source teardown-order correction,
        preserved in the WebRTC-era CameraWebRtcBranch.teardown() at the
        time and carried forward into CameraHlsBranch.teardown() when
        ADR-031 replaced it) -- it is a separate, real,
        independently-confirmed ownership gap, fixed here once,
        permanently, at the one place every future per-camera subsystem
        should also hook into rather than inventing its own ad hoc
        cleanup (or forgetting one, as these three did)."""
        self._policies.pop(camera_id, None)
        self._last_health_flush.pop(camera_id, None)
        self._runtime_adapter.forget_camera(camera_id)

        async def _run() -> None:
            try:
                await self.live_stream_manager.remove_camera(camera_id)
            except Exception:
                logger.exception("Live Monitoring failed to fully remove camera %s", camera_id)
            try:
                await self.runtime_supervisor.remove_camera(camera_id)
            except Exception:
                logger.exception("RuntimeSupervisor failed to fully remove camera %s", camera_id)

        self._bridge.schedule(_run())

    def _on_health_snapshot(self, camera_id: uuid.UUID, status: Any, fps: float | None) -> None:
        """HeartbeatScheduler's on_health_snapshot hook -- fires every
        heartbeat tick (default 1s). Throttled here to
        observed_state_flush_interval_seconds (default 3s) before actually
        persisting, per the write-volume constraint: high-frequency metrics
        must not be written every tick. Skipped entirely for a
        non-CONNECTED camera (nothing meaningful to persist). Latency is a
        single pipeline-wide rolling average (PerformanceInstrumentation
        has no per-camera figure today), applied to every connected camera
        -- a known simplification, not a per-camera measurement."""
        if status != "CONNECTED":
            return
        now = time.monotonic()
        last_flush = self._last_health_flush.get(camera_id)
        if last_flush is not None and (
            now - last_flush < self._settings.observed_state_flush_interval_seconds
        ):
            return
        self._last_health_flush[camera_id] = now
        latency_ms = self._instrumentation.snapshot().end_to_end_latency_ms
        task = asyncio.get_event_loop().create_task(
            self._runtime_adapter.persist_health_snapshot(camera_id, fps=fps, latency_ms=latency_ms)
        )
        self._observed_state_flush_tasks.add(task)
        task.add_done_callback(self._observed_state_flush_tasks.discard)

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

    async def _sample_telemetry_forever(self) -> None:
        """RM-12 Camera Runtime Step 5 activation: Telemetry is
        observational-only and was designed with no HTTP endpoint of its
        own (see telemetry.py's module docstring) -- periodic logging,
        mirroring _sample_metrics_forever's identical established pattern,
        is the mechanism by which its snapshot() becomes observable at all
        until a real endpoint exists."""
        try:
            while True:
                await asyncio.sleep(self._settings.metrics_sample_interval_seconds)
                logger.info("Camera Runtime telemetry snapshot: %s", self.telemetry.snapshot())
        except asyncio.CancelledError:
            pass

    async def _synchronize_desired_state_forever(self) -> None:
        """RM-12 Camera Runtime v1: temporary polling loop, until a later
        milestone replaces it with event-driven synchronization (see
        synchronization.py's module docstring -- Step 4 deliberately shipped
        with no automatic trigger). Reuses
        DesiredStateSynchronizer.synchronize() exactly as implemented; this
        method adds no reconciliation logic of its own, only the periodic
        call. Skips a tick if the previous synchronize() call from this same
        loop is still running, rather than allowing overlapping calls. Logs
        only when synchronize() actually did something (SynchronizationResult's
        own docstring: empty actions_taken means already converged) or when
        it raises -- no per-tick spam on the common no-op case."""
        try:
            while True:
                await asyncio.sleep(self._settings.desired_state_sync_interval_seconds)
                if self._desired_state_sync_running:
                    continue
                self._desired_state_sync_running = True
                try:
                    result = await self.desired_state_synchronizer.synchronize()
                    if result.actions_taken:
                        logger.info("Desired State synchronization: %s", result.actions_taken)
                except Exception:
                    logger.exception("Desired State synchronization failed")
                finally:
                    self._desired_state_sync_running = False
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._metrics_task is not None:
            self._metrics_task.cancel()
            self._metrics_task = None
        if self._telemetry_task is not None:
            self._telemetry_task.cancel()
            self._telemetry_task = None
        if self._desired_state_sync_task is not None:
            self._desired_state_sync_task.cancel()
            self._desired_state_sync_task = None
        self.telemetry.stop()
        await self.live_stream_manager.stop()
        await self.media_publisher.shutdown()
        await self.runtime_supervisor.stop()
        if self._heartbeat is not None:
            self._heartbeat.stop()
        self._pipeline.stop()
        self._bridge.stop()
        await self._bus.stop()

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
        plain FrameObservation values cross the bridge, to RuntimeAdapter's
        own scheduled consumer (see the module docstring).

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
        # self._policies is only pre-populated in start() for cameras
        # already active at startup -- a camera added later (the normal
        # case: any registered camera) has no entry yet. Lazily create one
        # here rather than requiring every add_source path to remember to
        # do it.
        policy = self._policies.setdefault(
            source.camera_id,
            ReconnectPolicy(
                initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
                max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
                multiplier=self._settings.reconnect_backoff_multiplier,
            ),
        )
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
            succeeded_after_attempt = policy.attempt_count
            policy.reset()
            # Promotion to CONNECTED now happens via _on_source_first_buffer
            # (add_source() above attaches a fresh one-shot probe to the new
            # bin) -- not here, the same Observed-State-accuracy fix as the
            # initial-add path. Status stays RECONNECTING (set above, before
            # this retry attempt) until a real buffer actually arrives.
            _audit_logger.info(
                "Pipeline Restarted: camera=%s attempt=%d",
                source.camera_id,
                succeeded_after_attempt,
            )
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
