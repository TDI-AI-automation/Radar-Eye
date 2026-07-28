"""Tests for apps.deepstream.app.telemetry -- RM-12 Camera Runtime Step 5
(Telemetry: observational-only liveness/readiness/metrics collection).

Pure asyncio -- no DeepStream SDK, no database. Two layers: isolated tests
against small fakes (liveness/readiness computation, collector lifecycle,
metric plumbing) and integration tests wiring the *real* RuntimeSupervisor
and DesiredStateSynchronizer in (mirroring test_synchronization.py's own
"validate the real seam, not a mock" philosophy) to prove Telemetry's
counters genuinely reflect what those components actually did.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable

import pytest

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.desired_state import DesiredCameraState
from apps.deepstream.app.ingestion.camera_registry import CameraSource
from apps.deepstream.app.ingestion.source import RtspSource, valve_element_name
from apps.deepstream.app.runtime_supervisor import ConcurrentEnableLimiter, RuntimeSupervisor
from apps.deepstream.app.synchronization import DesiredStateSynchronizer
from apps.deepstream.app.telemetry import TelemetryCollector

# ---------------------------------------------------------------------------
# Fakes for isolated tests
# ---------------------------------------------------------------------------


class FakePipeline:
    def __init__(self, *, built: bool = True, active: frozenset[uuid.UUID] = frozenset()) -> None:
        self._built = built
        self._active = active

    def is_built(self) -> bool:
        return self._built

    def active_camera_ids(self) -> frozenset[uuid.UUID]:
        return self._active


class FakeRuntimeSupervisor:
    def __init__(self) -> None:
        self._ai_enabled: frozenset[uuid.UUID] = frozenset()
        self._queued = 0
        self._workers_alive = True
        self.valve_transition_count = 0
        self.runtime_error_count = 0
        self.last_command_latency_ms: float | None = None

    def ai_enabled_camera_ids(self) -> frozenset[uuid.UUID]:
        return self._ai_enabled

    def queued_command_count(self) -> int:
        return self._queued

    def all_workers_alive(self) -> bool:
        return self._workers_alive


class FakeSynchronizer:
    def __init__(self) -> None:
        self.synchronization_count = 0
        self.last_synchronization_duration_seconds: float | None = None
        self.last_read_succeeded: bool | None = None


class FakeBridge:
    def __init__(self, *, running: bool = True) -> None:
        self.is_running = running


def _make_collector(
    *,
    pipeline: FakePipeline | None = None,
    supervisor: FakeRuntimeSupervisor | None = None,
    synchronizer: FakeSynchronizer | None = None,
    bridge: FakeBridge | None = None,
    tick_interval_seconds: float = 0.01,
) -> TelemetryCollector:
    return TelemetryCollector(
        pipeline=pipeline or FakePipeline(),
        runtime_supervisor=supervisor or FakeRuntimeSupervisor(),
        synchronizer=synchronizer or FakeSynchronizer(),
        bridge=bridge or FakeBridge(),
        tick_interval_seconds=tick_interval_seconds,
    )


@pytest.mark.asyncio
class TestLivenessTransitions:
    async def test_event_loop_responsive_is_false_before_start(self) -> None:
        collector = _make_collector()
        assert collector.liveness().event_loop_responsive is False

    async def test_event_loop_responsive_is_true_after_start(self) -> None:
        collector = _make_collector()
        collector.start()
        try:
            assert collector.liveness().event_loop_responsive is True
        finally:
            collector.stop()

    async def test_event_loop_responsive_is_false_after_stop(self) -> None:
        collector = _make_collector()
        collector.start()
        collector.stop()
        assert collector.liveness().event_loop_responsive is False

    async def test_background_workers_alive_reflects_runtime_supervisor(self) -> None:
        supervisor = FakeRuntimeSupervisor()
        collector = _make_collector(supervisor=supervisor)

        assert collector.liveness().background_workers_alive is True
        supervisor._workers_alive = False
        assert collector.liveness().background_workers_alive is False

    async def test_process_alive_is_always_true(self) -> None:
        assert _make_collector().liveness().process_alive is True

    async def test_alive_property_requires_all_three_components(self) -> None:
        collector = _make_collector()
        collector.start()
        try:
            assert collector.liveness().alive is True
        finally:
            collector.stop()
        assert collector.liveness().alive is False  # event loop no longer responsive


@pytest.mark.asyncio
class TestReadinessTransitions:
    async def test_pipeline_ready_reflects_is_built(self) -> None:
        pipeline = FakePipeline(built=False)
        collector = _make_collector(pipeline=pipeline)
        assert collector.readiness().pipeline_ready is False

        pipeline._built = True
        assert collector.readiness().pipeline_ready is True

    async def test_bridge_ready_reflects_bridge_is_running(self) -> None:
        bridge = FakeBridge(running=False)
        collector = _make_collector(bridge=bridge)
        assert collector.readiness().bridge_ready is False

        bridge.is_running = True
        assert collector.readiness().bridge_ready is True

    async def test_database_ready_is_true_until_a_read_fails(self) -> None:
        synchronizer = FakeSynchronizer()
        collector = _make_collector(synchronizer=synchronizer)
        assert collector.readiness().database_ready is True  # None -- never read yet

        synchronizer.last_read_succeeded = True
        assert collector.readiness().database_ready is True

        synchronizer.last_read_succeeded = False
        assert collector.readiness().database_ready is False

    async def test_ready_property_requires_every_component(self) -> None:
        pipeline = FakePipeline(built=False)
        collector = _make_collector(pipeline=pipeline)
        assert collector.readiness().ready is False

        pipeline._built = True
        assert collector.readiness().ready is True

    async def test_readiness_may_be_false_while_liveness_is_true(self) -> None:
        pipeline = FakePipeline(built=False)
        collector = _make_collector(pipeline=pipeline)
        collector.start()
        try:
            assert collector.liveness().alive is True
            assert collector.readiness().ready is False
        finally:
            collector.stop()


@pytest.mark.asyncio
class TestCollectorLifecycle:
    async def test_start_twice_raises(self) -> None:
        collector = _make_collector()
        collector.start()
        try:
            with pytest.raises(RuntimeError, match="already started"):
                collector.start()
        finally:
            collector.stop()

    async def test_stop_before_start_is_a_no_op(self) -> None:
        collector = _make_collector()
        collector.stop()  # must not raise

    async def test_stop_twice_is_a_no_op(self) -> None:
        collector = _make_collector()
        collector.start()
        collector.stop()
        collector.stop()  # must not raise

    async def test_tick_count_increases_while_running(self) -> None:
        collector = _make_collector(tick_interval_seconds=0.01)
        collector.start()
        try:
            for _ in range(20):
                if collector.snapshot().tick_count >= 2:
                    break
                await asyncio.sleep(0.01)
            assert collector.snapshot().tick_count >= 2
        finally:
            collector.stop()

    async def test_tick_count_stops_increasing_after_stop(self) -> None:
        collector = _make_collector(tick_interval_seconds=0.01)
        collector.start()
        await asyncio.sleep(0.03)
        collector.stop()
        count_at_stop = collector.snapshot().tick_count
        await asyncio.sleep(0.05)
        assert collector.snapshot().tick_count == count_at_stop


@pytest.mark.asyncio
class TestMetricUpdatesAndAggregation:
    async def test_active_camera_count_reflects_pipeline(self) -> None:
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pipeline = FakePipeline(active=frozenset({camera_a}))
        collector = _make_collector(pipeline=pipeline)
        assert collector.snapshot().active_camera_count == 1

        pipeline._active = frozenset({camera_a, camera_b})
        assert collector.snapshot().active_camera_count == 2

    async def test_valve_transition_count_aggregates_across_operations(self) -> None:
        supervisor = FakeRuntimeSupervisor()
        collector = _make_collector(supervisor=supervisor)
        assert collector.snapshot().valve_transition_count == 0

        supervisor.valve_transition_count += 1
        supervisor.valve_transition_count += 1
        supervisor.valve_transition_count += 1
        assert collector.snapshot().valve_transition_count == 3

    async def test_runtime_error_count_aggregates_across_failures(self) -> None:
        supervisor = FakeRuntimeSupervisor()
        collector = _make_collector(supervisor=supervisor)

        supervisor.runtime_error_count += 1
        assert collector.snapshot().runtime_error_count == 1
        supervisor.runtime_error_count += 1
        assert collector.snapshot().runtime_error_count == 2

    async def test_synchronization_count_aggregates(self) -> None:
        synchronizer = FakeSynchronizer()
        collector = _make_collector(synchronizer=synchronizer)

        synchronizer.synchronization_count = 5
        assert collector.snapshot().synchronization_count == 5

    async def test_pipeline_build_time_is_none_without_instrumentation(self) -> None:
        collector = _make_collector()
        assert collector.snapshot().pipeline_build_time_seconds is None

    async def test_pipeline_build_time_reads_from_instrumentation(self) -> None:
        class FakeSnapshot:
            pipeline_startup_seconds = 12.5

        class FakeInstrumentation:
            def snapshot(self) -> FakeSnapshot:
                return FakeSnapshot()

        collector = TelemetryCollector(
            pipeline=FakePipeline(),
            runtime_supervisor=FakeRuntimeSupervisor(),
            synchronizer=FakeSynchronizer(),
            bridge=FakeBridge(),
            instrumentation=FakeInstrumentation(),
        )
        assert collector.snapshot().pipeline_build_time_seconds == 12.5


@pytest.mark.asyncio
class TestConcurrentMetricPublication:
    async def test_concurrent_snapshots_while_producers_mutate_do_not_crash(self) -> None:
        supervisor = FakeRuntimeSupervisor()
        collector = _make_collector(supervisor=supervisor)
        stop = asyncio.Event()

        async def _mutator() -> None:
            while not stop.is_set():
                supervisor.valve_transition_count += 1
                await asyncio.sleep(0)

        async def _reader() -> list[int]:
            counts = []
            for _ in range(200):
                counts.append(collector.snapshot().valve_transition_count)
                await asyncio.sleep(0)
            return counts

        mutator_task = asyncio.create_task(_mutator())
        readers = await asyncio.gather(_reader(), _reader(), _reader())
        stop.set()
        await mutator_task

        for counts in readers:
            assert len(counts) == 200
            assert all(isinstance(c, int) and c >= 0 for c in counts)
            assert counts == sorted(counts)  # monotonically non-decreasing


@pytest.mark.asyncio
class TestFailureReporting:
    async def test_database_not_ready_after_a_failed_read(self) -> None:
        synchronizer = FakeSynchronizer()
        synchronizer.last_read_succeeded = False
        collector = _make_collector(synchronizer=synchronizer)

        snapshot = collector.snapshot()
        assert snapshot.readiness.database_ready is False
        assert snapshot.readiness.ready is False

    async def test_runtime_errors_do_not_affect_liveness_or_readiness(self) -> None:
        """Telemetry must never let a reported failure metric itself
        influence the liveness/readiness computation for unrelated
        components -- runtime_error_count is purely informational."""
        supervisor = FakeRuntimeSupervisor()
        supervisor.runtime_error_count = 100
        collector = _make_collector(supervisor=supervisor)

        assert collector.liveness().background_workers_alive is True
        assert collector.readiness().ready is True


# ---------------------------------------------------------------------------
# Integration tests: real RuntimeSupervisor / DesiredStateSynchronizer
# ---------------------------------------------------------------------------


class FakeMainLoop:
    def __init__(self) -> None:
        self._stop = threading.Event()

    def run(self) -> None:
        self._stop.wait(timeout=5)

    def quit(self) -> None:
        self._stop.set()


def _immediate_idle_add(callback: Callable[[], bool]) -> int:
    callback()
    return 0


def _make_bridge(loop: asyncio.AbstractEventLoop) -> AsyncBridge:
    bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=_immediate_idle_add)
    bridge.start()
    return bridge


class FakeValve:
    def __init__(self) -> None:
        self.drop: bool | None = None

    def set_property(self, name: str, value: bool) -> None:
        self.drop = value


class FakeBin:
    def __init__(self, camera_id: uuid.UUID) -> None:
        self.camera_id = camera_id
        self.valve = FakeValve()

    def get_by_name(self, name: str) -> FakeValve | None:
        return self.valve if name == valve_element_name(self.camera_id) else None


class RealisticFakePipeline:
    """Satisfies both RuntimeSupervisor's PipelineHandle and Telemetry's
    TelemetryPipeline Protocols -- used to wire a *real* RuntimeSupervisor
    into a real TelemetryCollector."""

    def __init__(self) -> None:
        self._bins: dict[uuid.UUID, FakeBin] = {}
        self._built = True

    def is_built(self) -> bool:
        return self._built

    def bin_for(self, camera_id: uuid.UUID) -> FakeBin | None:
        return self._bins.get(camera_id)

    def active_camera_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(self._bins.keys())

    def add_source(self, source: RtspSource) -> None:
        camera_id = source.camera.camera_id
        self._bins[camera_id] = FakeBin(camera_id)

    def remove_source(self, camera_id: uuid.UUID) -> None:
        self._bins.pop(camera_id, None)


class FakeDesiredStateReader:
    def __init__(self, states: list[DesiredCameraState]) -> None:
        self.states = states
        self.should_fail = False

    async def read_all(self) -> list[DesiredCameraState]:
        if self.should_fail:
            raise ConnectionError("simulated database failure")
        return list(self.states)


def _desired(camera_id: uuid.UUID, *, ai_enabled: bool = False) -> DesiredCameraState:
    return DesiredCameraState(
        camera_id=camera_id,
        name="test-camera",
        lifecycle_state="OPERATIONAL",
        ai_enabled=ai_enabled,
        recording_enabled=False,
        rtsp_url="rtsp://192.0.2.1:554/stream",
        transport="tcp",
    )


@pytest.mark.asyncio
class TestRuntimeSupervisorIntegration:
    async def test_snapshot_reflects_real_runtime_supervisor_activity(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = RealisticFakePipeline()
        pipeline.add_source(RtspSource(camera=CameraSource(camera_id, "cam", "rtsp://x", "tcp")))
        bridge = _make_bridge(loop)
        supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=4))
        synchronizer_stub = FakeSynchronizer()

        collector = TelemetryCollector(
            pipeline=pipeline,
            runtime_supervisor=supervisor,
            synchronizer=synchronizer_stub,
            bridge=bridge,
        )

        assert collector.snapshot().valve_transition_count == 0
        assert collector.snapshot().ai_enabled_camera_count == 0

        await supervisor.enable_ai(camera_id)

        snapshot = collector.snapshot()
        assert snapshot.valve_transition_count == 1
        assert snapshot.ai_enabled_camera_count == 1
        assert snapshot.last_command_latency_ms is not None

        await supervisor.enable_ai(camera_id)  # idempotent no-op
        assert collector.snapshot().valve_transition_count == 1  # unchanged

        await supervisor.disable_ai(camera_id)
        snapshot = collector.snapshot()
        assert snapshot.valve_transition_count == 2
        assert snapshot.ai_enabled_camera_count == 0

    async def test_queued_command_count_reflects_real_backlog(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = RealisticFakePipeline()
        pipeline.add_source(RtspSource(camera=CameraSource(camera_id, "cam", "rtsp://x", "tcp")))

        blocked = asyncio.Event()

        def idle_add(callback: Callable[[], bool]) -> int:
            async def _deferred() -> None:
                await blocked.wait()
                callback()

            loop.create_task(_deferred())
            return 0

        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=idle_add)
        bridge.start()
        supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=4))
        collector = TelemetryCollector(
            pipeline=pipeline,
            runtime_supervisor=supervisor,
            synchronizer=FakeSynchronizer(),
            bridge=bridge,
        )

        task1 = asyncio.create_task(supervisor.enable_ai(camera_id))  # will block in idle_add
        await asyncio.sleep(0)
        task2 = asyncio.create_task(supervisor.disable_ai(camera_id))  # queued behind it
        for _ in range(3):
            await asyncio.sleep(0)

        assert collector.snapshot().queued_command_count == 1

        blocked.set()
        await asyncio.gather(task1, task2)
        assert collector.snapshot().queued_command_count == 0


@pytest.mark.asyncio
class TestSynchronizationMetricsIntegration:
    async def test_synchronization_metrics_reflect_real_synchronizer(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = RealisticFakePipeline()
        bridge = _make_bridge(loop)
        supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=4))
        reader = FakeDesiredStateReader([_desired(camera_id)])
        synchronizer = DesiredStateSynchronizer(reader, pipeline, bridge, supervisor)

        collector = TelemetryCollector(
            pipeline=pipeline,
            runtime_supervisor=supervisor,
            synchronizer=synchronizer,
            bridge=bridge,
        )

        assert collector.snapshot().synchronization_count == 0
        assert collector.snapshot().readiness.database_ready is True  # never read yet -- not False

        await synchronizer.synchronize()

        snapshot = collector.snapshot()
        assert snapshot.synchronization_count == 1
        assert snapshot.last_synchronization_duration_seconds is not None
        assert snapshot.readiness.database_ready is True
        assert snapshot.active_camera_count == 1

        await synchronizer.synchronize()
        assert collector.snapshot().synchronization_count == 2

    async def test_database_readiness_reflects_a_real_read_failure(self) -> None:
        loop = asyncio.get_running_loop()
        pipeline = RealisticFakePipeline()
        bridge = _make_bridge(loop)
        supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=4))
        reader = FakeDesiredStateReader([])
        reader.should_fail = True
        synchronizer = DesiredStateSynchronizer(reader, pipeline, bridge, supervisor)

        collector = TelemetryCollector(
            pipeline=pipeline,
            runtime_supervisor=supervisor,
            synchronizer=synchronizer,
            bridge=bridge,
        )

        with pytest.raises(ConnectionError):
            await synchronizer.synchronize()  # Telemetry must not swallow this

        snapshot = collector.snapshot()
        assert snapshot.readiness.database_ready is False
        assert snapshot.readiness.ready is False
        assert snapshot.synchronization_count == 0  # counted only on completion, not a failed read
