"""Tests for apps.deepstream.app.runtime_supervisor -- RM-12 Camera Runtime
Step 3 (Runtime Supervisor: per-camera command queue, EnableAI/DisableAI,
GPU admission, AsyncBridge scheduling, idempotency).

Pure asyncio -- no DeepStream/GStreamer SDK needed. A real ``AsyncBridge``
is used throughout (its own cross-thread contract is already covered by
test_bridge.py), injected with a fake main loop and a fake ``idle_add`` so
these tests can control exactly when a scheduled valve mutation actually
"reaches the GLib thread" -- the same injection technique test_bridge.py
already established for ``mainloop_factory``.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable

import pytest

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.ingestion.source import valve_element_name
from apps.deepstream.app.runtime_supervisor import (
    CommandOutcome,
    ConcurrentEnableLimiter,
    RuntimeSupervisor,
    RuntimeSupervisorError,
)


class FakeMainLoop:
    def __init__(self) -> None:
        self._stop = threading.Event()

    def run(self) -> None:
        self._stop.wait(timeout=5)

    def quit(self) -> None:
        self._stop.set()


class FakeValve:
    def __init__(self) -> None:
        self.drop: bool | None = None
        self.set_calls: list[bool] = []

    def set_property(self, name: str, value: bool) -> None:
        assert name == "drop"
        self.drop = value
        self.set_calls.append(value)


class FakeBin:
    def __init__(self, camera_id: uuid.UUID) -> None:
        self.camera_id = camera_id
        self.valve = FakeValve()

    def get_by_name(self, name: str) -> FakeValve | None:
        return self.valve if name == valve_element_name(self.camera_id) else None


class FakePipeline:
    def __init__(self) -> None:
        self._bins: dict[uuid.UUID, FakeBin] = {}

    def add_camera(self, camera_id: uuid.UUID) -> FakeBin:
        bin_ = FakeBin(camera_id)
        self._bins[camera_id] = bin_
        return bin_

    def bin_for(self, camera_id: uuid.UUID) -> FakeBin | None:
        return self._bins.get(camera_id)


class AlwaysAdmit:
    def __init__(self) -> None:
        self.admitted: list[uuid.UUID] = []
        self.released: list[uuid.UUID] = []

    def try_admit(self, camera_id: uuid.UUID) -> bool:
        self.admitted.append(camera_id)
        return True

    def release(self, camera_id: uuid.UUID) -> None:
        self.released.append(camera_id)


def _immediate_idle_add(callback: Callable[[], bool]) -> int:
    callback()
    return 0


def _make_bridge(
    loop: asyncio.AbstractEventLoop,
    *,
    idle_add: Callable[[Callable[[], bool]], int] = _immediate_idle_add,
) -> AsyncBridge:
    bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=idle_add)
    bridge.start()
    return bridge


@pytest.mark.asyncio
class TestValveStateTransitions:
    async def test_enable_ai_opens_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        outcome = await supervisor.enable_ai(camera_id)

        assert outcome == CommandOutcome(accepted=True)
        assert bin_.valve.drop is False

    async def test_disable_ai_closes_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        await supervisor.enable_ai(camera_id)
        outcome = await supervisor.disable_ai(camera_id)

        assert outcome == CommandOutcome(accepted=True)
        assert bin_.valve.drop is True

    async def test_disable_ai_on_a_fresh_camera_actually_closes_the_valve(self) -> None:
        """A freshly built source bin's valve starts physically *open*
        (Source Manager, Step 1: drop=False at construction) -- Runtime
        Supervisor's own bookkeeping for a camera it has never commanded
        starts unknown, not "already disabled", so the first DisableAI must
        still perform a real mutation rather than a false-idempotent no-op
        (found via real hardware validation: the very first DisableAI in a
        toggle sequence was silently skipped before this was fixed)."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        outcome = await supervisor.disable_ai(camera_id)

        assert outcome == CommandOutcome(accepted=True, reason=None)
        assert bin_.valve.set_calls == [True]  # actually closed, not skipped

    async def test_disable_ai_on_a_fresh_camera_is_idempotent_thereafter(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        first = await supervisor.disable_ai(camera_id)
        second = await supervisor.disable_ai(camera_id)

        assert first == CommandOutcome(accepted=True, reason=None)
        assert second == CommandOutcome(accepted=True, reason="already disabled")
        assert bin_.valve.set_calls == [True]  # only the first call mutated

    async def test_missing_source_bin_raises(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()  # camera never added
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        with pytest.raises(RuntimeSupervisorError):
            await supervisor.enable_ai(camera_id)


@pytest.mark.asyncio
class TestValveChangedHook:
    """Generic, optional hook fired at the one place every valve mutation
    already funnels through -- currently unused by Live Monitoring's
    HLS branch (apps/deepstream/app/live_stream/, ADR-030/031: AI-
    annotated-only, no runtime source switch to drive), but the hook
    itself remains a supported RuntimeSupervisor extension point."""

    async def test_hook_is_optional(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        await supervisor.enable_ai(camera_id)  # no on_valve_changed=... -- must not raise

    async def test_hook_fires_true_on_enable_and_false_on_disable(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        calls: list[tuple[uuid.UUID, bool]] = []
        supervisor = RuntimeSupervisor(
            pipeline,
            _make_bridge(loop),
            AlwaysAdmit(),
            on_valve_changed=lambda cid, active: calls.append((cid, active)),
        )

        await supervisor.enable_ai(camera_id)
        await supervisor.disable_ai(camera_id)

        assert calls == [(camera_id, True), (camera_id, False)]

    async def test_hook_does_not_fire_on_idempotent_no_op(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        calls: list[tuple[uuid.UUID, bool]] = []
        supervisor = RuntimeSupervisor(
            pipeline,
            _make_bridge(loop),
            AlwaysAdmit(),
            on_valve_changed=lambda cid, active: calls.append((cid, active)),
        )

        await supervisor.enable_ai(camera_id)
        await supervisor.enable_ai(camera_id)  # already enabled -- no real mutation

        assert calls == [(camera_id, True)]


@pytest.mark.asyncio
class TestIdempotency:
    async def test_repeated_enable_is_a_deterministic_no_op(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        admission = AlwaysAdmit()
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)

        first = await supervisor.enable_ai(camera_id)
        second = await supervisor.enable_ai(camera_id)

        assert first == CommandOutcome(accepted=True)
        assert second == CommandOutcome(accepted=True, reason="already enabled")
        assert bin_.valve.set_calls == [False]  # only one mutation
        assert admission.admitted == [camera_id]  # only admitted once

    async def test_repeated_disable_is_a_deterministic_no_op(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        await supervisor.enable_ai(camera_id)
        first = await supervisor.disable_ai(camera_id)
        second = await supervisor.disable_ai(camera_id)

        assert first == CommandOutcome(accepted=True)
        assert second == CommandOutcome(accepted=True, reason="already disabled")
        assert bin_.valve.set_calls == [False, True]  # only one close

    async def test_repeated_enable_disable_cycles(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        for _ in range(5):
            await supervisor.enable_ai(camera_id)
            await supervisor.disable_ai(camera_id)

        assert bin_.valve.set_calls == [False, True] * 5
        assert bin_.valve.drop is True


@pytest.mark.asyncio
class TestAdmission:
    async def test_admission_accepted_opens_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        admission = ConcurrentEnableLimiter(max_concurrent=1)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)

        outcome = await supervisor.enable_ai(camera_id)

        assert outcome == CommandOutcome(accepted=True)
        assert bin_.valve.drop is False

    async def test_admission_rejected_leaves_the_valve_unchanged(self) -> None:
        loop = asyncio.get_running_loop()
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pipeline = FakePipeline()
        bin_a = pipeline.add_camera(camera_a)
        bin_b = pipeline.add_camera(camera_b)
        admission = ConcurrentEnableLimiter(max_concurrent=1)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)

        outcome_a = await supervisor.enable_ai(camera_a)
        outcome_b = await supervisor.enable_ai(camera_b)

        assert outcome_a.accepted is True
        assert outcome_b == CommandOutcome(accepted=False, reason="GPU admission rejected")
        assert bin_a.valve.drop is False
        assert bin_b.valve.set_calls == []  # never mutated

    async def test_release_on_disable_frees_admission_for_another_camera(self) -> None:
        loop = asyncio.get_running_loop()
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_a)
        bin_b = pipeline.add_camera(camera_b)
        admission = ConcurrentEnableLimiter(max_concurrent=1)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)

        await supervisor.enable_ai(camera_a)
        await supervisor.disable_ai(camera_a)
        outcome_b = await supervisor.enable_ai(camera_b)

        assert outcome_b == CommandOutcome(accepted=True)
        assert bin_b.valve.drop is False


@pytest.mark.asyncio
class TestAsyncBridgeScheduling:
    async def test_valve_mutation_only_happens_once_the_bridge_actually_runs_it(self) -> None:
        """Proves the mutation is *scheduled* through AsyncBridge rather
        than called directly -- the valve stays untouched until the
        captured callback is invoked, exactly as it would sit unexecuted on
        a real GLib main loop's idle queue until that loop gets to it."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        captured: list[Callable[[], bool]] = []
        reached = asyncio.Event()

        def idle_add(callback: Callable[[], bool]) -> int:
            captured.append(callback)
            reached.set()
            return 0

        supervisor = RuntimeSupervisor(
            pipeline, _make_bridge(loop, idle_add=idle_add), AlwaysAdmit()
        )

        task = asyncio.create_task(supervisor.enable_ai(camera_id))
        await asyncio.wait_for(reached.wait(), timeout=1)

        assert bin_.valve.drop is None  # not yet mutated
        assert len(captured) == 1

        captured[0]()  # simulate the GLib main loop actually running the idle callback
        outcome = await asyncio.wait_for(task, timeout=1)

        assert outcome.accepted is True
        assert bin_.valve.drop is False


@pytest.mark.asyncio
class TestCommandOrdering:
    async def test_commands_for_the_same_camera_execute_in_submission_order(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        bin_ = pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        # enable, disable, enable -- fired without awaiting between them.
        t1 = asyncio.create_task(supervisor.enable_ai(camera_id))
        t2 = asyncio.create_task(supervisor.disable_ai(camera_id))
        t3 = asyncio.create_task(supervisor.enable_ai(camera_id))

        o1, o2, o3 = await asyncio.gather(t1, t2, t3)

        assert [o1.accepted, o2.accepted, o3.accepted] == [True, True, True]
        assert bin_.valve.set_calls == [False, True, False]
        assert bin_.valve.drop is False


@pytest.mark.asyncio
class TestConcurrentCamerasDoNotBlockEachOther:
    async def test_a_slow_camera_does_not_delay_another_cameras_command(self) -> None:
        loop = asyncio.get_running_loop()
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_a)
        bin_b = pipeline.add_camera(camera_b)

        camera_a_reached = asyncio.Event()
        release_camera_a = asyncio.Event()
        calls = 0

        def idle_add(callback: Callable[[], bool]) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                camera_a_reached.set()

                async def _deferred() -> None:
                    await release_camera_a.wait()
                    callback()

                loop.create_task(_deferred())
            else:
                callback()
            return 0

        supervisor = RuntimeSupervisor(
            pipeline, _make_bridge(loop, idle_add=idle_add), AlwaysAdmit()
        )

        task_a = asyncio.create_task(supervisor.enable_ai(camera_a))
        await asyncio.wait_for(camera_a_reached.wait(), timeout=1)

        # Camera A's command is stuck "on the GLib thread" -- camera B's
        # own worker/queue is entirely independent and must still complete.
        outcome_b = await asyncio.wait_for(supervisor.enable_ai(camera_b), timeout=1)
        assert outcome_b.accepted is True
        assert bin_b.valve.drop is False
        assert not task_a.done()

        release_camera_a.set()
        outcome_a = await asyncio.wait_for(task_a, timeout=1)
        assert outcome_a.accepted is True


@pytest.mark.asyncio
class TestTeardown:
    async def test_stop_rejects_in_flight_and_queued_commands(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)

        in_flight_reached = asyncio.Event()
        never_released = asyncio.Event()  # deliberately never set

        def idle_add(callback: Callable[[], bool]) -> int:
            in_flight_reached.set()

            async def _blocks_forever() -> None:
                await never_released.wait()
                callback()

            loop.create_task(_blocks_forever())
            return 0

        supervisor = RuntimeSupervisor(
            pipeline, _make_bridge(loop, idle_add=idle_add), AlwaysAdmit()
        )

        in_flight_task = asyncio.create_task(supervisor.enable_ai(camera_id))
        await asyncio.wait_for(in_flight_reached.wait(), timeout=1)

        queued_task = asyncio.create_task(supervisor.disable_ai(camera_id))
        for _ in range(3):
            await asyncio.sleep(0)  # let the disable command actually enqueue

        await asyncio.wait_for(supervisor.stop(), timeout=2)

        # RuntimeSupervisorError, not CancelledError: in_flight_task/queued_task
        # are different asyncio Tasks than the ones stop() itself cancels
        # (worker.task) -- delivering a raw CancelledError to an unrelated
        # awaiter risks it being misread as a request to cancel that task
        # too (see _run_worker's own comment; this is the hardware-confirmed
        # bug that silently killed DesiredStateSynchronizer's forever-loop).
        with pytest.raises(RuntimeSupervisorError):
            await in_flight_task
        with pytest.raises(RuntimeSupervisorError):
            await queued_task

    async def test_stop_is_safe_with_no_workers(self) -> None:
        loop = asyncio.get_running_loop()
        pipeline = FakePipeline()
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        await supervisor.stop()  # must not raise


@pytest.mark.asyncio
class TestRemoveCamera:
    """Root-cause coverage for the Operator Acceptance Testing ownership
    audit (2026-08-03): before remove_camera() existed, nothing ever
    removed a deleted camera's worker from _workers -- it sat forever,
    blocked on its own empty queue, one permanent leaked entry per
    operator delete/re-register cycle."""

    async def test_removes_the_worker_entirely(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())
        await supervisor.enable_ai(camera_id)
        assert camera_id in supervisor.worker_camera_ids()

        await supervisor.remove_camera(camera_id)

        assert camera_id not in supervisor.worker_camera_ids()

    async def test_releases_gpu_admission_if_ai_was_enabled(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        admission = AlwaysAdmit()
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)
        await supervisor.enable_ai(camera_id)
        assert admission.released == []

        await supervisor.remove_camera(camera_id)

        assert admission.released == [camera_id]

    async def test_does_not_double_release_admission_when_already_disabled(self) -> None:
        """disable_ai() itself already calls release() unconditionally on
        every real convergence to closed (harmless no-op for a set-based
        admission tracker even when nothing was ever admitted) --
        remove_camera() must not add a second, redundant release on top
        of that for a worker that is already known to be AI-disabled."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)
        admission = AlwaysAdmit()
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), admission)
        await supervisor.disable_ai(camera_id)
        assert admission.released == [camera_id]  # disable_ai's own release

        await supervisor.remove_camera(camera_id)

        assert admission.released == [camera_id]  # unchanged -- no double release

    async def test_is_a_no_op_for_a_camera_with_no_worker(self) -> None:
        loop = asyncio.get_running_loop()
        pipeline = FakePipeline()
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())

        await supervisor.remove_camera(uuid.uuid4())  # must not raise

    async def test_does_not_disturb_another_camera_s_worker(self) -> None:
        loop = asyncio.get_running_loop()
        removed_id, kept_id = uuid.uuid4(), uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(removed_id)
        pipeline.add_camera(kept_id)
        supervisor = RuntimeSupervisor(pipeline, _make_bridge(loop), AlwaysAdmit())
        await supervisor.enable_ai(removed_id)
        await supervisor.enable_ai(kept_id)

        await supervisor.remove_camera(removed_id)

        assert supervisor.worker_camera_ids() == frozenset({kept_id})
        assert supervisor.ai_enabled_camera_ids() == frozenset({kept_id})

    async def test_rejects_a_queued_command_for_the_removed_camera(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        pipeline = FakePipeline()
        pipeline.add_camera(camera_id)

        in_flight_reached = asyncio.Event()
        never_released = asyncio.Event()  # deliberately never set

        def idle_add(callback: Callable[[], bool]) -> int:
            in_flight_reached.set()

            async def _blocks_forever() -> None:
                await never_released.wait()
                callback()

            loop.create_task(_blocks_forever())
            return 0

        supervisor = RuntimeSupervisor(
            pipeline, _make_bridge(loop, idle_add=idle_add), AlwaysAdmit()
        )

        in_flight_task = asyncio.create_task(supervisor.enable_ai(camera_id))
        await asyncio.wait_for(in_flight_reached.wait(), timeout=1)
        queued_task = asyncio.create_task(supervisor.disable_ai(camera_id))
        for _ in range(3):
            await asyncio.sleep(0)  # let the disable command actually enqueue

        await asyncio.wait_for(supervisor.remove_camera(camera_id), timeout=2)

        # RuntimeSupervisorError, not CancelledError -- see
        # test_stop_rejects_in_flight_and_queued_commands's comment: these
        # are different asyncio Tasks than the one remove_camera() itself
        # cancels (worker.task).
        with pytest.raises(RuntimeSupervisorError):
            await in_flight_task
        with pytest.raises(RuntimeSupervisorError):
            await queued_task
        assert camera_id not in supervisor.worker_camera_ids()
