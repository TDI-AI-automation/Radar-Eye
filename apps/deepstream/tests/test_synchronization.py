"""Tests for apps.deepstream.app.synchronization -- RM-12 Camera Runtime
Step 4 (Desired State -> Runtime convergence).

Pure asyncio -- no DeepStream SDK, no database. A real ``AsyncBridge`` (fake
main loop/idle_add, same convention as test_runtime_supervisor.py) and a
real ``RuntimeSupervisor`` are used against a self-contained fake pipeline,
so these tests validate the real seam between DesiredStateSynchronizer and
RuntimeSupervisor, not a mocked stand-in for it -- exactly the kind of
integration gap that a mock would have hidden in Step 3's own
now-fixed ai_enabled bootstrap defect.
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
        assert name == "drop"
        self.drop = value


class FakeBin:
    def __init__(self, camera_id: uuid.UUID) -> None:
        self.camera_id = camera_id
        self.valve = FakeValve()

    def get_by_name(self, name: str) -> FakeValve | None:
        return self.valve if name == valve_element_name(self.camera_id) else None


class FakePipeline:
    def __init__(self) -> None:
        self._bins: dict[uuid.UUID, FakeBin] = {}
        self.add_source_calls: list[uuid.UUID] = []
        self.remove_source_calls: list[uuid.UUID] = []

    def bin_for(self, camera_id: uuid.UUID) -> FakeBin | None:
        return self._bins.get(camera_id)

    def active_camera_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(self._bins.keys())

    def add_source(self, source: RtspSource) -> None:
        camera_id = source.camera.camera_id
        self._bins[camera_id] = FakeBin(camera_id)
        self.add_source_calls.append(camera_id)

    def remove_source(self, camera_id: uuid.UUID) -> None:
        self._bins.pop(camera_id, None)
        self.remove_source_calls.append(camera_id)


class FakeDesiredStateReader:
    def __init__(self, states: list[DesiredCameraState]) -> None:
        self.states = states

    async def read_all(self) -> list[DesiredCameraState]:
        return list(self.states)


def _desired(
    camera_id: uuid.UUID,
    *,
    lifecycle_state: str = "OPERATIONAL",
    ai_enabled: bool = False,
    recording_enabled: bool = False,
    has_profile: bool = True,
) -> DesiredCameraState:
    return DesiredCameraState(
        camera_id=camera_id,
        name="test-camera",
        lifecycle_state=lifecycle_state,  # type: ignore[arg-type]
        ai_enabled=ai_enabled,
        recording_enabled=recording_enabled,
        rtsp_url="rtsp://192.0.2.1:554/stream" if has_profile else None,
        transport="tcp" if has_profile else None,
    )


def _make_synchronizer(
    loop: asyncio.AbstractEventLoop,
    states: list[DesiredCameraState],
    *,
    lifecycle_policy: object | None = None,
) -> tuple[DesiredStateSynchronizer, FakePipeline, FakeDesiredStateReader]:
    pipeline = FakePipeline()
    bridge = _make_bridge(loop)
    supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=10))
    reader = FakeDesiredStateReader(states)
    synchronizer = DesiredStateSynchronizer(
        reader, pipeline, bridge, supervisor, lifecycle_policy=lifecycle_policy  # type: ignore[arg-type]
    )
    return synchronizer, pipeline, reader


@pytest.mark.asyncio
class TestStartupSynchronization:
    async def test_operational_camera_gets_a_source(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id)])

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert f"add_source:{camera_id}" in result.actions_taken

    async def test_draft_camera_gets_a_source_but_ai_stays_off(self) -> None:
        """Camera Connectivity and AI Runtime are independent (Operator
        Acceptance Testing finding): a DRAFT camera connects immediately
        -- even with ai_enabled=True, AI must not run until the camera is
        promoted to OPERATIONAL."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, lifecycle_state="DRAFT", ai_enabled=True)]
        )

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert f"add_source:{camera_id}" in result.actions_taken
        assert f"enable_ai:{camera_id}" not in result.actions_taken
        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]

    @pytest.mark.parametrize("lifecycle_state", ["TESTING", "VERIFIED", "MAINTENANCE"])
    async def test_non_operational_non_disabled_camera_connects_but_ai_stays_off(
        self, lifecycle_state: str
    ) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, lifecycle_state=lifecycle_state, ai_enabled=True)]
        )

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert f"enable_ai:{camera_id}" not in result.actions_taken
        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]

    async def test_disabled_camera_gets_no_source(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, lifecycle_state="DISABLED")]
        )

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == []
        assert result.actions_taken == ()

    async def test_operational_and_ai_enabled_opens_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id, ai_enabled=True)])

        await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]

    async def test_operational_and_ai_disabled_closes_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, ai_enabled=False)]
        )

        await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]


@pytest.mark.asyncio
class TestIdempotentRefresh:
    async def test_repeated_synchronize_with_unchanged_state_does_no_extra_work(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id, ai_enabled=True)])

        first = await synchronizer.synchronize()
        second = await synchronizer.synchronize()

        assert first.actions_taken != ()
        assert second.actions_taken == ()
        assert pipeline.add_source_calls == [camera_id]  # only once

    async def test_source_already_present_is_not_re_added(self) -> None:
        """A camera whose source was already built by something other than
        this synchronizer (e.g. pre-existing runtime state at process
        start) must not be re-added just because synchronize() has never
        run before -- only the lifecycle/source half of convergence is
        "already satisfied" here; RuntimeSupervisor's own AI-state
        bookkeeping is still fresh for this camera, so its first touch
        still performs one real valve mutation (Step 3's own, already
        -accepted idempotency semantics -- not re-tested here)."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        desired = _desired(camera_id, ai_enabled=True)
        synchronizer, pipeline, _ = _make_synchronizer(loop, [desired])
        pipeline.add_source(
            RtspSource(
                camera=CameraSource(
                    camera_id=camera_id,
                    name=desired.name,
                    rtsp_url=desired.rtsp_url,  # type: ignore[arg-type]
                    transport=desired.transport,  # type: ignore[arg-type]
                )
            )
        )

        calls_before_synchronize = list(pipeline.add_source_calls)
        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == calls_before_synchronize  # unchanged
        assert f"add_source:{camera_id}" not in result.actions_taken
        bin_ = pipeline.bin_for(camera_id)
        assert bin_ is not None
        assert bin_.valve.drop is False  # AI convergence still ran


@pytest.mark.asyncio
class TestDesiredStateChanges:
    async def test_lifecycle_operational_to_disabled_removes_the_source(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(loop, [_desired(camera_id)])
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id) is not None

        reader.states = [_desired(camera_id, lifecycle_state="DISABLED")]
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id) is None
        assert pipeline.remove_source_calls == [camera_id]
        assert f"remove_source:{camera_id}" in result.actions_taken

    async def test_lifecycle_draft_to_operational_enables_ai_without_recreating_the_source(
        self,
    ) -> None:
        """A DRAFT camera is already connected (Camera Connectivity is
        independent of lifecycle except DISABLED) -- promoting it to
        OPERATIONAL must only change AI eligibility, never tear down and
        rebuild the source."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(
            loop, [_desired(camera_id, lifecycle_state="DRAFT", ai_enabled=True)]
        )
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id) is not None
        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]
        calls_before = list(pipeline.add_source_calls)

        reader.states = [_desired(camera_id, lifecycle_state="OPERATIONAL", ai_enabled=True)]
        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == calls_before  # no re-add
        assert f"add_source:{camera_id}" not in result.actions_taken
        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]
        assert f"enable_ai:{camera_id}" in result.actions_taken

    async def test_ai_enabled_transition_opens_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(
            loop, [_desired(camera_id, ai_enabled=False)]
        )
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]

        reader.states = [_desired(camera_id, ai_enabled=True)]
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]
        assert f"enable_ai:{camera_id}" in result.actions_taken

    async def test_ai_disabled_transition_closes_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(
            loop, [_desired(camera_id, ai_enabled=True)]
        )
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]

        reader.states = [_desired(camera_id, ai_enabled=False)]
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]
        assert f"disable_ai:{camera_id}" in result.actions_taken

    async def test_lifecycle_operational_to_maintenance_closes_the_valve_but_keeps_the_source(
        self,
    ) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(
            loop, [_desired(camera_id, ai_enabled=True)]
        )
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]
        calls_before = list(pipeline.add_source_calls)

        reader.states = [_desired(camera_id, lifecycle_state="MAINTENANCE", ai_enabled=True)]
        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == calls_before  # source untouched
        assert pipeline.bin_for(camera_id) is not None
        assert pipeline.bin_for(camera_id).valve.drop is True  # type: ignore[union-attr]
        assert f"disable_ai:{camera_id}" in result.actions_taken


@pytest.mark.asyncio
class TestRecordingFlagPersistence:
    async def test_recording_desired_is_tracked_without_any_runtime_behavior(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, recording_enabled=True)]
        )

        assert synchronizer.recording_desired(camera_id) is None  # never seen yet

        await synchronizer.synchronize()

        assert synchronizer.recording_desired(camera_id) is True
        # No recording-related pipeline call exists on the fake at all --
        # if synchronize() tried to invoke one, this test would fail to
        # construct/collect, not silently pass.
        assert pipeline.add_source_calls == [camera_id]  # only the lifecycle action

    async def test_recording_desired_updates_across_refreshes(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, _pipeline, reader = _make_synchronizer(
            loop, [_desired(camera_id, recording_enabled=False)]
        )
        await synchronizer.synchronize()
        assert synchronizer.recording_desired(camera_id) is False

        reader.states = [_desired(camera_id, recording_enabled=True)]
        await synchronizer.synchronize()
        assert synchronizer.recording_desired(camera_id) is True


@pytest.mark.asyncio
class TestMissingAndRemovedCameras:
    async def test_operational_camera_with_no_stream_profile_is_skipped(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id, has_profile=False)]
        )

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == []
        assert result.actions_taken == ()

    async def test_camera_no_longer_in_desired_state_has_its_source_removed(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, reader = _make_synchronizer(loop, [_desired(camera_id)])
        await synchronizer.synchronize()
        assert pipeline.bin_for(camera_id) is not None

        reader.states = []  # camera no longer appears in Desired State at all
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id) is None
        assert pipeline.remove_source_calls == [camera_id]
        assert f"remove_source:{camera_id}" in result.actions_taken


@pytest.mark.asyncio
class TestPartialConvergence:
    async def test_each_camera_converges_independently_in_one_pass(self) -> None:
        loop = asyncio.get_running_loop()
        needs_add, needs_remove, needs_enable, already_fine = (
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
        )
        synchronizer, pipeline, reader = _make_synchronizer(
            loop,
            [
                _desired(needs_remove),
                _desired(needs_enable, ai_enabled=False),
                _desired(already_fine, ai_enabled=True),
            ],
        )
        # Bootstrap: needs_remove/needs_enable/already_fine all start converged
        # (source present, AI matching); needs_add doesn't exist anywhere yet.
        await synchronizer.synchronize()

        reader.states = [
            _desired(needs_remove, lifecycle_state="DISABLED"),
            _desired(needs_enable, ai_enabled=True),
            _desired(already_fine, ai_enabled=True),  # unchanged
            _desired(needs_add),  # new camera
        ]
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(needs_remove) is None
        assert pipeline.bin_for(needs_enable).valve.drop is False  # type: ignore[union-attr]
        assert pipeline.bin_for(already_fine).valve.drop is False  # type: ignore[union-attr]
        assert pipeline.bin_for(needs_add) is not None
        assert f"remove_source:{needs_remove}" in result.actions_taken
        assert f"enable_ai:{needs_enable}" in result.actions_taken
        assert f"add_source:{needs_add}" in result.actions_taken
        assert not any(str(already_fine) in action for action in result.actions_taken)


@pytest.mark.asyncio
class TestLifecyclePolicyIsInjectable:
    """The synchronizer must depend on a LifecycleSourcePolicy, not embed
    lifecycle-state judgment inline -- proven here by swapping in a policy
    that treats a non-default state as active, with zero changes to
    DesiredStateSynchronizer itself."""

    async def test_custom_policy_overrides_the_default_active_state_set(self) -> None:
        class AlwaysActivePolicy:
            def should_have_active_source(self, lifecycle_state: str) -> bool:
                return True

            def should_allow_ai(self, lifecycle_state: str) -> bool:
                return False

        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(
            loop,
            [_desired(camera_id, lifecycle_state="DRAFT")],
            lifecycle_policy=AlwaysActivePolicy(),
        )

        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id) is not None
        assert f"add_source:{camera_id}" in result.actions_taken
