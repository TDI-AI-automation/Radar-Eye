"""Validation watchdog -- RM-11.SIV.

Purpose: visibility only, NOT recovery (explicit requirement in the RM-11.SIV
approval). Periodically compares every named component's ``HeartbeatStatus``
(read from the shared ``HeartbeatRegistry`` -- the Unified Heartbeat
requirement's single source of truth, also consumed by
``siv/dashboard.py``) against ``configs/validation.yaml``'s per-component
staleness threshold, and logs exactly which stage stopped, for how long,
and what its last known activity was.

Two components don't come from a heartbeat beat:
  - "pipeline_fps": read directly from
    ``PerformanceInstrumentation.snapshot().inference_fps`` -- a rate, not a
    liveness timestamp, so "stale" here means "no recent frames counted
    into the rolling FPS window" rather than "no beat within N seconds".
  - "event_bus": this watchdog subscribes itself to every known event type
    (via the public ``EventBus.subscribe`` API -- no core EventBus change)
    and beats "event_bus" on the *same* shared HeartbeatRegistry whenever
    any event arrives, so it still reads back through the one source of
    truth like everything else.

Never mutates pipeline state, never reconnects anything, never restarts any
component -- it only observes and logs.
"""

from __future__ import annotations

import asyncio
import logging
import time

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry, HeartbeatStatus
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.stage_logging import get_audit_logger
from shared.events.bus import EventBus
from shared.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)
_audit_logger = get_audit_logger()

_MONITORED_EVENT_TYPES = (
    "ThreatAssessmentEvent",
    "HumanReviewItemCreatedEvent",
    "IncidentCreatedEvent",
    "IncidentUpdatedEvent",
    "AlarmRequestedEvent",
    "SnapshotCreatedEvent",
    "ClipCreatedEvent",
    "CameraDisconnectedEvent",
    "CalibrationUpdatedEvent",
    "SystemEvent",
)
"""Every event type in shared/events/types.py -- subscribing to all of them
is how the watchdog observes "EventBus alive" without EventBus itself
needing to know a watchdog exists."""

_EVENT_BUS_COMPONENT = "event_bus"

_HEARTBEAT_COMPONENTS = (
    "camera",
    "rtsp",
    "pgie",
    "tracker",
    "sgie",
    "runtime_adapter",
    "threat_runtime_adapter",
    "threat_engine",
    "calibration",
    "incident",
    "alarm",
    "heartbeat",
)
"""Components fed by HeartbeatRegistry.beat() calls elsewhere in the
pipeline. "pipeline_fps" and "event_bus" are handled separately -- see the
module docstring."""


class Watchdog:
    def __init__(
        self,
        *,
        heartbeat_registry: HeartbeatRegistry,
        instrumentation: PerformanceInstrumentation,
        settings: WatchdogSettings,
        bus: EventBus | None = None,
    ) -> None:
        self._heartbeat = heartbeat_registry
        self._instrumentation = instrumentation
        self._settings = settings
        self._bus = bus
        self._task: asyncio.Task[None] | None = None
        self._previously_healthy: dict[str, bool] = {}
        self._last_frames_processed = 0
        self._last_frames_processed_at = time.monotonic()

        if bus is not None:
            for event_type in _MONITORED_EVENT_TYPES:
                bus.subscribe(event_type, self._on_any_event, name="watchdog")

    async def _on_any_event(self, _event: EventEnvelope) -> None:
        self._heartbeat.beat(_EVENT_BUS_COMPONENT)

    def check_once(self) -> dict[str, HeartbeatStatus]:
        """Runs one full check across every monitored component and logs
        (once, on the falling edge) when a component transitions from
        healthy to stale. Public -- tests and the dashboard call this
        directly without waiting on the real interval."""
        thresholds = self._settings.stale_after_seconds
        statuses: dict[str, HeartbeatStatus] = {}

        for component in _HEARTBEAT_COMPONENTS:
            threshold = getattr(thresholds, component)
            statuses[component] = self._heartbeat.status(component, stale_after_seconds=threshold)

        statuses["event_bus"] = self._heartbeat.status(
            _EVENT_BUS_COMPONENT, stale_after_seconds=thresholds.event_bus
        )
        statuses["pipeline_fps"] = self._pipeline_fps_status(thresholds.pipeline_fps)

        for component, status in statuses.items():
            was_healthy = self._previously_healthy.get(component, True)
            if was_healthy and not status.healthy:
                _audit_logger.warning(
                    "Watchdog Warning: %s stalled -- last activity %.1fs ago (%s)",
                    component,
                    status.age_seconds(),
                    status.reason,
                )
            self._previously_healthy[component] = status.healthy

        return statuses

    def _pipeline_fps_status(self, stale_after_seconds: float) -> HeartbeatStatus:
        """Unlike the beat-fed components, there is no explicit "a frame
        was processed" event to hook here -- instead this tracks
        ``frames_processed`` (from the same PerformanceInstrumentation
        snapshot RM-11 Phase 1 already exposes) across successive checks,
        comparing time-since-last-change against the threshold. Same
        staleness semantics as every other component, just derived rather
        than beaten directly."""
        now = time.monotonic()
        snapshot = self._instrumentation.snapshot()
        if snapshot.frames_processed == 0:
            return HeartbeatStatus(
                component="pipeline_fps",
                last_seen_monotonic=now,
                counter=0,
                healthy=False,
                reason="no frames processed yet",
            )
        if snapshot.frames_processed != self._last_frames_processed:
            self._last_frames_processed = snapshot.frames_processed
            self._last_frames_processed_at = now

        age = now - self._last_frames_processed_at
        healthy = age <= stale_after_seconds
        reason = None
        if not healthy:
            reason = f"no new frames in {age:.1f}s (fps={snapshot.inference_fps})"
        return HeartbeatStatus(
            component="pipeline_fps",
            last_seen_monotonic=self._last_frames_processed_at,
            counter=snapshot.frames_processed,
            healthy=healthy,
            reason=reason,
        )

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._settings.check_interval_seconds)
                try:
                    self.check_once()
                except Exception:
                    logger.exception("Watchdog.check_once() failed")
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("Watchdog is already started")
        self._task = asyncio.get_event_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
