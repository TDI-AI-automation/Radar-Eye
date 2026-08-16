"""Telemetry -- RM-12 Camera Runtime Step 5.

Observability only. ``TelemetryCollector`` reads state that Camera Runtime's
other components (``DeepStreamPipeline``, ``RuntimeSupervisor``,
``DesiredStateSynchronizer``, ``AsyncBridge``) already own for their own
reasons -- every metric here has one of those as its defined producer (see
each component's own Step 5 additions: a handful of read-only counters/
accessors, purely additive, never consulted by that component's own control
flow). This module never calls ``enable_ai``/``disable_ai``/``synchronize``/
``add_source``/``remove_source`` or any other state-changing method on
anything it reads from -- it has no write path into Camera Runtime at all.

GPU admission remains owned by Runtime Supervisor; Desired State remains
owned by Camera Registry. Telemetry only reports.

Explicitly out of scope for this milestone: broker transport, Media
Publisher, Recording, Streaming, alerting, dashboards. No HTTP endpoint is
exposed here -- apps/deepstream has no HTTP server of its own today (see
the still-open RM-14 process-composition question); ``liveness()``/
``readiness()``/``snapshot()`` are the queryable state a future endpoint
(once RM-14 settles process composition) would simply call.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class TelemetryPipeline(Protocol):
    def is_built(self) -> bool: ...

    def active_camera_ids(self) -> frozenset[uuid.UUID]: ...


class TelemetryRuntimeSupervisor(Protocol):
    def ai_enabled_camera_ids(self) -> frozenset[uuid.UUID]: ...

    def queued_command_count(self) -> int: ...

    def all_workers_alive(self) -> bool: ...

    @property
    def valve_transition_count(self) -> int: ...

    @property
    def runtime_error_count(self) -> int: ...

    @property
    def last_command_latency_ms(self) -> float | None: ...


class TelemetrySynchronizer(Protocol):
    @property
    def synchronization_count(self) -> int: ...

    @property
    def last_synchronization_duration_seconds(self) -> float | None: ...

    @property
    def last_read_succeeded(self) -> bool | None: ...


class TelemetryBridge(Protocol):
    @property
    def is_running(self) -> bool: ...


class TelemetryInstrumentation(Protocol):
    """What Telemetry needs from ``PerformanceInstrumentation`` (RM-11) --
    a single, already-tracked fact (pipeline build time), read rather than
    re-derived. Optional: a caller with no instrumentation instance simply
    reports ``pipeline_build_time_seconds=None``."""

    def snapshot(self) -> Any: ...


@dataclass(frozen=True)
class LivenessState:
    """ "Is this process alive?" -- see module docstring's Health Model."""

    process_alive: bool
    event_loop_responsive: bool
    background_workers_alive: bool

    @property
    def alive(self) -> bool:
        return self.process_alive and self.event_loop_responsive and self.background_workers_alive


@dataclass(frozen=True)
class ReadinessState:
    """ "Can this node perform useful work?" -- may be false while liveness
    remains true (e.g. the pipeline hasn't finished building yet, but the
    process and its background workers are fine)."""

    pipeline_ready: bool
    runtime_supervisor_ready: bool
    bridge_ready: bool
    event_bus_ready: bool
    database_ready: bool

    @property
    def ready(self) -> bool:
        return all(
            (
                self.pipeline_ready,
                self.runtime_supervisor_ready,
                self.bridge_ready,
                self.event_bus_ready,
                self.database_ready,
            )
        )


@dataclass(frozen=True)
class TelemetrySnapshot:
    liveness: LivenessState
    readiness: ReadinessState
    active_camera_count: int
    ai_enabled_camera_count: int
    queued_command_count: int
    valve_transition_count: int
    runtime_error_count: int
    last_command_latency_ms: float | None
    synchronization_count: int
    last_synchronization_duration_seconds: float | None
    pipeline_build_time_seconds: float | None
    tick_count: int


class TelemetryCollector:
    """Aggregates observational state from Camera Runtime's other
    components. Owns a periodic background tick purely to prove the
    asyncio loop it runs on is still responsive (``LivenessState
    .event_loop_responsive``) -- the tick computes nothing else;
    ``snapshot()`` always pulls fresh values directly from each producer,
    never from a cache the tick maintains."""

    def __init__(
        self,
        *,
        pipeline: TelemetryPipeline,
        runtime_supervisor: TelemetryRuntimeSupervisor,
        synchronizer: TelemetrySynchronizer,
        bridge: TelemetryBridge,
        instrumentation: TelemetryInstrumentation | None = None,
        tick_interval_seconds: float = 5.0,
    ) -> None:
        self._pipeline = pipeline
        self._runtime_supervisor = runtime_supervisor
        self._synchronizer = synchronizer
        self._bridge = bridge
        self._instrumentation = instrumentation
        self._tick_interval_seconds = tick_interval_seconds
        self._tick_count = 0
        self._task: asyncio.Task[None] | None = None

    def snapshot(self) -> TelemetrySnapshot:
        liveness = LivenessState(
            process_alive=True,  # trivially true -- this code is executing
            event_loop_responsive=self._task is not None and not self._task.done(),
            background_workers_alive=self._runtime_supervisor.all_workers_alive(),
        )
        readiness = ReadinessState(
            pipeline_ready=self._pipeline.is_built(),
            # Constructed and injected -- always available once this object exists.
            runtime_supervisor_ready=True,
            bridge_ready=self._bridge.is_running,
            # No live connectivity check implemented yet -- RM-14 process
            # composition (whether apps.api/apps.deepstream share one bus)
            # is still an open question.
            event_bus_ready=True,
            database_ready=self._synchronizer.last_read_succeeded is not False,
        )
        pipeline_build_time: float | None = None
        if self._instrumentation is not None:
            pipeline_build_time = self._instrumentation.snapshot().pipeline_startup_seconds

        return TelemetrySnapshot(
            liveness=liveness,
            readiness=readiness,
            active_camera_count=len(self._pipeline.active_camera_ids()),
            ai_enabled_camera_count=len(self._runtime_supervisor.ai_enabled_camera_ids()),
            queued_command_count=self._runtime_supervisor.queued_command_count(),
            valve_transition_count=self._runtime_supervisor.valve_transition_count,
            runtime_error_count=self._runtime_supervisor.runtime_error_count,
            last_command_latency_ms=self._runtime_supervisor.last_command_latency_ms,
            synchronization_count=self._synchronizer.synchronization_count,
            last_synchronization_duration_seconds=(
                self._synchronizer.last_synchronization_duration_seconds
            ),
            pipeline_build_time_seconds=pipeline_build_time,
            tick_count=self._tick_count,
        )

    def liveness(self) -> LivenessState:
        return self.snapshot().liveness

    def readiness(self) -> ReadinessState:
        return self.snapshot().readiness

    async def _tick_forever(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_interval_seconds)
                self._tick_count += 1
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("TelemetryCollector is already started")
        self._task = asyncio.get_event_loop().create_task(self._tick_forever())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
