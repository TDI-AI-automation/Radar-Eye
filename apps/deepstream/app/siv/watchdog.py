"""Validation watchdog -- RM-11.SIV.

Purpose: visibility only, NOT recovery (explicit requirement in the RM-11.SIV
approval). Periodically compares every named component's ``HeartbeatStatus``
(read from the shared ``HeartbeatRegistry`` -- the Unified Heartbeat
requirement's single source of truth, also consumed by
``siv/dashboard.py``) against ``configs/validation.yaml``'s per-component
staleness threshold, and logs exactly which stage stopped, for how long,
and what its last known activity was.

One component doesn't come from a beat recorded elsewhere in the pipeline:
  - "event_bus": this watchdog subscribes itself to every known event type
    (via the public ``EventBus.subscribe`` API -- no core EventBus change)
    and beats "event_bus" on the *same* shared HeartbeatRegistry whenever
    any event arrives, so it still reads back through the one source of
    truth like everything else.

"pipeline_fps" WAS handled as a separately-derived value (tracking
frames_processed across checks internally to this class) until a real
hardware run caught the resulting inconsistency: the dashboard, which only
ever reads HeartbeatRegistry directly, showed pipeline_fps permanently
stalled even while the watchdog itself correctly reported it healthy,
because the derived state never got written back to the shared registry --
exactly the kind of drift the Unified Heartbeat requirement's "one source
of truth" rule exists to prevent. Fixed by having
RuntimeAdapter.on_frame_observation beat "pipeline_fps" directly (see
runtime_adapter.py) -- it is now a plain beat-fed component like every
other one below.

Never mutates pipeline state, never reconnects anything, never restarts any
component -- it only observes and logs.
"""

from __future__ import annotations

import asyncio
import logging

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry, HeartbeatStatus
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
    "pipeline_fps",
)
"""Components fed by HeartbeatRegistry.beat() calls elsewhere in the
pipeline. "event_bus" is handled separately -- see the module docstring."""


class Watchdog:
    def __init__(
        self,
        *,
        heartbeat_registry: HeartbeatRegistry,
        settings: WatchdogSettings,
        bus: EventBus | None = None,
    ) -> None:
        self._heartbeat = heartbeat_registry
        self._settings = settings
        self._bus = bus
        self._task: asyncio.Task[None] | None = None
        self._previously_healthy: dict[str, bool] = {}

        if bus is not None:
            for event_type in _MONITORED_EVENT_TYPES:
                bus.subscribe(event_type, self._on_any_event, name="watchdog")

    async def _on_any_event(self, _event: EventEnvelope) -> None:
        self._heartbeat.beat(_EVENT_BUS_COMPONENT)

    def check_once(self, *, now: float | None = None) -> dict[str, HeartbeatStatus]:
        """Runs one full check across every monitored component and logs
        (once, on the falling edge) when a component transitions from
        healthy to stale. Public -- tests and the dashboard call this
        directly without waiting on the real interval.

        ``now`` mirrors ``HeartbeatRegistry.status``'s injectable clock
        reading -- defaults to the real monotonic clock; tests use it to
        force staleness deterministically instead of racing real elapsed
        time against a near-zero threshold."""
        thresholds = self._settings.stale_after_seconds
        statuses: dict[str, HeartbeatStatus] = {}

        for component in _HEARTBEAT_COMPONENTS:
            threshold = getattr(thresholds, component)
            statuses[component] = self._heartbeat.status(
                component, stale_after_seconds=threshold, now=now
            )

        statuses["event_bus"] = self._heartbeat.status(
            _EVENT_BUS_COMPONENT, stale_after_seconds=thresholds.event_bus, now=now
        )

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
