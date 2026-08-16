"""Tests for apps.deepstream.app.synchronization -- RM-12 Camera Runtime
Step 4 (Desired State -> Runtime convergence).

Pure asyncio -- no DeepStream SDK, no database. A real ``AsyncBridge`` (fake
main loop/idle_add, same convention as test_runtime_supervisor.py) and a
real ``RuntimeSupervisor`` are used against a self-contained fake pipeline,
so these tests validate the real seam between DesiredStateSynchronizer and
RuntimeSupervisor, not a mocked stand-in for it -- exactly the kind of
integration gap that a mock would have hidden in Step 3's own
now-fixed ai_enabled bootstrap defect.

Lifecycle (DRAFT/TESTING/VERIFIED/OPERATIONAL/MAINTENANCE/DISABLED) has
been removed from the product entirely -- a registered camera always wants
an active source, and AI eligibility is ``ai_enabled`` alone. The only way
a camera stops being desired is deletion.
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
    ai_enabled: bool = False,
    recording_enabled: bool = False,
    has_profile: bool = True,
) -> DesiredCameraState:
    return DesiredCameraState(
        camera_id=camera_id,
        name="test-camera",
        ai_enabled=ai_enabled,
        recording_enabled=recording_enabled,
        rtsp_url="rtsp://192.0.2.1:554/stream" if has_profile else None,
        transport="tcp" if has_profile else None,
    )


def _make_synchronizer(
    loop: asyncio.AbstractEventLoop,
    states: list[DesiredCameraState],
    *,
    on_source_connected: Callable[[uuid.UUID], object] | None = None,
) -> tuple[DesiredStateSynchronizer, FakePipeline, FakeDesiredStateReader]:
    pipeline = FakePipeline()
    bridge = _make_bridge(loop)
    supervisor = RuntimeSupervisor(pipeline, bridge, ConcurrentEnableLimiter(max_concurrent=10))
    reader = FakeDesiredStateReader(states)
    synchronizer = DesiredStateSynchronizer(
        reader,
        pipeline,
        bridge,
        supervisor,
        on_source_connected=on_source_connected,  # type: ignore[arg-type]
    )
    return synchronizer, pipeline, reader


@pytest.mark.asyncio
class TestStartupSynchronization:
    async def test_registered_camera_gets_a_source(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id)])

        result = await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert f"add_source:{camera_id}" in result.actions_taken

    async def test_ai_enabled_camera_opens_the_valve(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id, ai_enabled=True)])

        await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id).valve.drop is False  # type: ignore[union-attr]

    async def test_ai_disabled_camera_keeps_the_valve_closed(self) -> None:
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
        run before -- only the source half of convergence is
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
        assert pipeline.add_source_calls == [camera_id]  # only the add_source action

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
    async def test_camera_with_no_stream_profile_is_skipped(self) -> None:
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

        reader.states = []  # camera deleted -- no longer appears in Desired State at all
        result = await synchronizer.synchronize()

        assert pipeline.bin_for(camera_id) is None
        assert pipeline.remove_source_calls == [camera_id]
        assert f"remove_source:{camera_id}" in result.actions_taken


@pytest.mark.asyncio
class TestPartialConvergence:
    async def test_each_camera_converges_independently_in_one_pass(self) -> None:
        loop = asyncio.get_running_loop()
        needs_remove, needs_enable, already_fine, needs_add = (
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
            # needs_remove deleted -- simply absent from the next read.
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
class TestOnSourceConnectedHook:
    """Real hardware bug (delete+re-register acceptance testing): a camera
    added on an *ongoing* convergence pass (not the initial one at process
    startup, and not the bus-error/EOS reconnect path) connected fine at
    the GStreamer level but never had RuntimeAdapter.on_camera_connected
    called for it -- so Observed State (what the operator's browser reads)
    stayed stuck at whatever it was before, and the UI never recovered.
    ``on_source_connected`` is the fix: fired exactly once per real
    add_source, regardless of which synchronize() call performed it."""

    async def test_fires_when_a_new_source_is_added(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        connected: list[uuid.UUID] = []

        async def _on_connected(cid: uuid.UUID) -> None:
            connected.append(cid)

        synchronizer, pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id)], on_source_connected=_on_connected
        )

        await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert connected == [camera_id]

    async def test_fires_on_a_later_pass_for_a_camera_added_after_startup(self) -> None:
        """The exact reported scenario: the first synchronize() pass has
        nothing to do for this camera (not desired yet -- e.g. it hasn't
        been (re-)registered), a later pass discovers it and adds it."""
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        connected: list[uuid.UUID] = []

        async def _on_connected(cid: uuid.UUID) -> None:
            connected.append(cid)

        synchronizer, pipeline, reader = _make_synchronizer(
            loop, [], on_source_connected=_on_connected
        )

        await synchronizer.synchronize()
        assert connected == []

        reader.states = [_desired(camera_id)]
        await synchronizer.synchronize()

        assert pipeline.add_source_calls == [camera_id]
        assert connected == [camera_id]

    async def test_does_not_fire_again_for_an_already_active_source(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        connected: list[uuid.UUID] = []

        async def _on_connected(cid: uuid.UUID) -> None:
            connected.append(cid)

        synchronizer, _pipeline, _ = _make_synchronizer(
            loop, [_desired(camera_id)], on_source_connected=_on_connected
        )

        await synchronizer.synchronize()
        await synchronizer.synchronize()

        assert connected == [camera_id]

    async def test_hook_is_optional(self) -> None:
        loop = asyncio.get_running_loop()
        camera_id = uuid.uuid4()
        synchronizer, pipeline, _ = _make_synchronizer(loop, [_desired(camera_id)])

        result = await synchronizer.synchronize()  # must not raise

        assert pipeline.add_source_calls == [camera_id]
        assert f"add_source:{camera_id}" in result.actions_taken
