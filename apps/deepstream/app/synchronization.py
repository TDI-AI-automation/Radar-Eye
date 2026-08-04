"""Desired State -> Runtime convergence -- RM-12 Camera Runtime Step 4.

``DesiredStateSynchronizer`` is the point where Camera Registry (Desired
State, read via ``DesiredStateReader``) and Camera Runtime (Observed/Runtime
state, read via ``PipelineHandle.bin_for``/``active_camera_ids`` and
converged via ``RuntimeSupervisor``) become architecturally connected.

It owns no read path of its own (``DesiredStateReader``'s job) and performs
no direct pipeline-element mutation of its own for AI state
(``RuntimeSupervisor``'s job, including that component's own idempotency --
this module never re-implements "is this camera already in the desired AI
state", it just decides *which* direction is desired and lets
``RuntimeSupervisor.enable_ai``/``disable_ai`` converge or no-op). It reads,
diffs, and dispatches the minimal set of actions -- reconciliation, not
imperative one-shot execution: calling ``synchronize()`` repeatedly with an
unchanged Desired State performs no additional work.

A registered camera always wants an active source -- there is no Lifecycle
state machine gating connectivity or AI eligibility (removed entirely;
Camera Connectivity is always maintained once a camera is registered, and
AI eligibility is ``ai_enabled`` alone). The only way a camera stops being
desired is deletion, handled by the "orphaned sources" sweep below.

Explicitly out of scope for Step 4 itself: broker-specific transport, Media
Publisher, Recording, Streaming, distributed coordination.
``synchronize()`` takes no transport-specific arguments and is safe to call
from anywhere (startup code, an explicit refresh request, or -- a later
milestone's job -- an EventBus subscription) without changing its
signature; Step 4 does not poll and does not wire any automatic trigger for
it. Step 5 (Telemetry) added the read-only counters/accessors near the
bottom of this class -- observational only, none of them feed back into
this class's own reconciliation decisions.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.desired_state import DesiredCameraState
from apps.deepstream.app.ingestion.camera_registry import CameraSource
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.runtime_supervisor import RuntimeSupervisor

logger = logging.getLogger(__name__)


class DesiredStateSource(Protocol):
    """What the synchronizer needs from ``DesiredStateReader`` -- a narrow
    Protocol (matching ``RuntimeSupervisor``'s own ``PipelineHandle``
    pattern) rather than a concrete-class dependency, so unit tests never
    need a real database to exercise reconciliation logic."""

    async def read_all(self) -> list[DesiredCameraState]: ...


class SynchronizablePipeline(Protocol):
    """The pipeline operations Desired State convergence needs -- a
    superset of ``runtime_supervisor.PipelineHandle`` (which only needs
    ``bin_for``). Kept as its own narrow Protocol rather than widening that
    one, so RuntimeSupervisor's own dependency stays minimal."""

    def bin_for(self, camera_id: uuid.UUID) -> Any | None: ...

    def active_camera_ids(self) -> frozenset[uuid.UUID]: ...

    def add_source(self, source: RtspSource) -> None: ...

    def remove_source(self, camera_id: uuid.UUID) -> None: ...


@dataclass(frozen=True)
class SynchronizationResult:
    """What one ``synchronize()`` pass actually did. Empty
    ``actions_taken`` means Runtime was already converged -- the expected,
    common-case result of a repeated refresh."""

    actions_taken: tuple[str, ...]


class DesiredStateSynchronizer:
    def __init__(
        self,
        reader: DesiredStateSource,
        pipeline: SynchronizablePipeline,
        bridge: AsyncBridge,
        runtime_supervisor: RuntimeSupervisor,
        *,
        on_source_connected: Callable[[uuid.UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._reader = reader
        self._pipeline = pipeline
        self._bridge = bridge
        self._runtime_supervisor = runtime_supervisor
        self._on_source_connected = on_source_connected
        """Optional, None-safe (same idiom as every other collaborator in
        this codebase) -- fires once a source this synchronizer itself
        just added actually finishes converging (real hardware bug,
        found via delete+re-register acceptance testing: the *only*
        other callers of RuntimeAdapter.on_camera_connected are
        runtime.py's own start() -- for cameras already active at
        process startup -- and the bus-error/EOS reconnect path for a
        camera that was already tracked. Neither covers a brand new
        camera_id this synchronizer discovers and adds on an *ongoing*
        convergence pass (e.g. a camera deleted and re-registered while
        the process keeps running) -- that source connects at the
        GStreamer level perfectly well, but Observed State (what the
        operator's browser actually reads) never gets persisted at all
        unless something calls RuntimeAdapter on its behalf.

        Observed-State-accuracy update: despite the name, this callback
        no longer marks the camera CONNECTED itself -- runtime.py wires
        it to mark RECONNECTING instead (a source was *added*, not yet
        *confirmed*; add_source() succeeding only means the GStreamer
        elements were constructed and linked, not that rtspsrc has
        actually finished its handshake with the camera). Promotion to
        CONNECTED happens separately, once a real buffer is observed
        flowing (DeepStreamPipeline's on_source_first_buffer hook, see
        runtime.py). This callback's own contract is unchanged: fire
        once per source this synchronizer just added, so it -- not
        just the initial-boot and reconnect paths -- also gets Observed
        State written for it."""
        self._recording_pending: dict[uuid.UUID, bool] = {}
        self._synchronization_count = 0
        self._last_synchronization_duration_seconds: float | None = None
        self._last_read_succeeded: bool | None = None
        """RM-12 Camera Runtime Step 5 (Telemetry) instrumentation -- read
        via the properties below, never consulted by this class's own
        reconciliation decisions. ``_last_read_succeeded`` reflects
        ``DesiredStateReader.read_all()``'s own outcome only (not the
        reconciliation actions taken afterward) -- a passive signal for
        Telemetry's database-readiness check, not a new active DB probe."""

    def recording_desired(self, camera_id: uuid.UUID) -> bool | None:
        """The most recently observed ``recording_enabled`` Desired State
        for this camera, or ``None`` if it has never been seen by a
        ``synchronize()`` call. No runtime behavior is triggered by this
        value in this milestone -- Recording (a later step) is the only
        intended consumer."""
        return self._recording_pending.get(camera_id)

    async def synchronize(self) -> SynchronizationResult:
        started_at = time.monotonic()
        try:
            desired_states = await self._reader.read_all()
        except Exception:
            self._last_read_succeeded = False
            raise
        self._last_read_succeeded = True

        try:
            desired_by_id = {state.camera_id: state for state in desired_states}
            actions: list[str] = []

            for desired in desired_states:
                actions.extend(await self._converge_one(desired))

            # Orphaned sources: active in the pipeline but the camera no
            # longer appears in Camera Registry's Desired State at all
            # (deleted). This is now the *only* way a source is removed --
            # a registered camera always wants an active source.
            active_ids = self._pipeline.active_camera_ids()
            for camera_id in active_ids:
                if camera_id not in desired_by_id:
                    await self._remove_source(camera_id)
                    actions.append(f"remove_source:{camera_id}")

            return SynchronizationResult(actions_taken=tuple(actions))
        finally:
            self._synchronization_count += 1
            self._last_synchronization_duration_seconds = time.monotonic() - started_at

    async def _converge_one(self, desired: DesiredCameraState) -> list[str]:
        actions: list[str] = []
        is_active = self._pipeline.bin_for(desired.camera_id) is not None

        if not is_active:
            if desired.rtsp_url is None or desired.transport is None:
                logger.warning(
                    "Camera %s (%s) has no camera_stream_profiles row -- " "cannot add a source",
                    desired.camera_id,
                    desired.name,
                )
            else:
                await self._ensure_source(desired)
                actions.append(f"add_source:{desired.camera_id}")
                is_active = True
                if self._on_source_connected is not None:
                    await self._on_source_connected(desired.camera_id)

        if is_active:
            if desired.ai_enabled:
                outcome = await self._runtime_supervisor.enable_ai(desired.camera_id)
            else:
                outcome = await self._runtime_supervisor.disable_ai(desired.camera_id)
            if outcome.reason is None:  # None -- a real mutation just converged it
                verb = "enable_ai" if desired.ai_enabled else "disable_ai"
                actions.append(f"{verb}:{desired.camera_id}")

        self._recording_pending[desired.camera_id] = desired.recording_enabled
        return actions

    async def _ensure_source(self, desired: DesiredCameraState) -> None:
        assert desired.rtsp_url is not None and desired.transport is not None
        source = RtspSource(
            camera=CameraSource(
                camera_id=desired.camera_id,
                name=desired.name,
                rtsp_url=desired.rtsp_url,
                transport=desired.transport,
            )
        )
        future = self._bridge.schedule_on_mainloop(lambda: self._pipeline.add_source(source))
        await asyncio.wrap_future(future)

    async def _remove_source(self, camera_id: uuid.UUID) -> None:
        future = self._bridge.schedule_on_mainloop(lambda: self._pipeline.remove_source(camera_id))
        await asyncio.wrap_future(future)

    # -- RM-12 Camera Runtime Step 5 (Telemetry): read-only accessors only.

    @property
    def synchronization_count(self) -> int:
        """Cumulative count of completed ``synchronize()`` calls (counted
        whether or not the read succeeded -- see ``last_read_succeeded``)."""
        return self._synchronization_count

    @property
    def last_synchronization_duration_seconds(self) -> float | None:
        return self._last_synchronization_duration_seconds

    @property
    def last_read_succeeded(self) -> bool | None:
        """``None`` until ``synchronize()`` has run at least once."""
        return self._last_read_succeeded
