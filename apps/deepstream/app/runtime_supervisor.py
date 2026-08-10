"""Runtime Supervisor -- RM-12 Camera Runtime Step 3.

Owns the only path by which anything mutates a camera's AI-gating valve
(``ingestion/source.py``'s Decision 2 element, ``pipeline/frame_distributor.py``'s
Step 2 tee sits upstream of it and is untouched by this module). Each camera
gets its own ``asyncio.Queue`` and a dedicated worker task -- fully
independent of every other camera's queue/worker (no global lock, no
cross-camera interference, no queue starvation: one camera's backlog can
never delay another's).

``EnableAI``/``DisableAI`` are declarative, idempotent intents, not
imperative one-shot actions: a repeated call while a camera is already in
the requested state is a deterministic no-op (no pipeline mutation, no
duplicate GPU admission bookkeeping) -- Runtime Supervisor behaves as a
state converger, not a blind command executor.

Every pipeline mutation (the one thing this module ever does to the valve)
is scheduled onto the GLib main-loop thread via
``AsyncBridge.schedule_on_mainloop`` -- this module never touches a
``Gst.Element`` from its own (asyncio) thread directly, matching
``bridge.py``'s "no module reaches across threads on its own" rule.

Explicitly out of scope for Step 3 itself: Desired State synchronization
(nothing here decides *when* to call EnableAI/DisableAI -- Step 4 wires
that in), Event Bus publication, Media Publisher, Recording, Streaming.
Step 5 (Telemetry) added the read-only counters/accessors near the bottom
of this class -- observational only, none of them feed back into this
class's own decisions.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from apps.deepstream.app.bridge import AsyncBridge
from apps.deepstream.app.ingestion.source import valve_element_name

logger = logging.getLogger(__name__)


class RuntimeSupervisorError(RuntimeError):
    """A command could not be executed for a reason that is not a normal,
    expected control-flow outcome (e.g. no active source bin for the
    camera) -- distinct from a GPU admission rejection, which is a routine,
    deterministic ``CommandOutcome``, not an error."""


@dataclass(frozen=True)
class CommandOutcome:
    """The result of one EnableAI/DisableAI command."""

    accepted: bool
    reason: str | None = None


class PipelineHandle(Protocol):
    """The one thing Runtime Supervisor needs from ``DeepStreamPipeline`` --
    see ``pipeline/builder.py``'s ``bin_for()``. A narrow Protocol rather
    than a concrete-class dependency, so unit tests never need the real
    pipeline (or the DeepStream SDK it eventually requires) to exercise
    command-queue/admission/idempotency logic."""

    def bin_for(self, camera_id: uuid.UUID) -> Any | None: ...


class GpuAdmissionHook(Protocol):
    """The extension point a future milestone is expected to feed live GPU
    utilization into (Step 5, Telemetry, is observational only and does not
    touch this -- GPU admission policy remains owned by Runtime Supervisor).
    ``try_admit`` is called
    once per EnableAI attempt that would actually change state (never for
    an idempotent no-op); a camera admitted via ``try_admit`` must later be
    ``release``d exactly once, when it stops being AI-enabled (DisableAI,
    or rollback after a failed valve mutation)."""

    def try_admit(self, camera_id: uuid.UUID) -> bool: ...

    def release(self, camera_id: uuid.UUID) -> None: ...


class ConcurrentEnableLimiter:
    """Default GPU admission policy: bounds how many cameras may have AI
    concurrently enabled system-wide, admitting a new EnableAI only below
    that ceiling. Deterministic and hardware-agnostic -- a genuine safeguard
    against many simultaneous EnableAI commands (across independently
    executing cameras) thrashing the shared GPU, per the Operational
    Semantics Review's GPU/command-queue fairness finding, without needing
    live GPU telemetry (explicitly out of this milestone's scope) to be
    useful. A future milestone is expected to supply a real
    utilization-based ``GpuAdmissionHook`` later (not Step 5, which is
    observational only and does not change GPU admission policy); this one
    is the seam it replaces, not a placeholder that does nothing."""

    def __init__(self, max_concurrent: int) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._max_concurrent = max_concurrent
        self._admitted: set[uuid.UUID] = set()

    def try_admit(self, camera_id: uuid.UUID) -> bool:
        if camera_id in self._admitted:
            return True
        if len(self._admitted) >= self._max_concurrent:
            return False
        self._admitted.add(camera_id)
        return True

    def release(self, camera_id: uuid.UUID) -> None:
        self._admitted.discard(camera_id)


@dataclass
class _QueuedCommand:
    enable: bool
    future: asyncio.Future[CommandOutcome]


class _CameraWorker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[_QueuedCommand] = asyncio.Queue()
        self.ai_enabled: bool | None = None
        """``None`` -- unknown -- until this worker's first command actually
        converges the valve. A freshly built source bin's valve starts
        physically *open* (Source Manager, Step 1: ``drop=False``,
        permanently, at construction), not closed -- so this must not
        default to ``False``, or a camera's very first DisableAI would be
        misread as an idempotent no-op against an already-open valve and
        silently never close it (found via real hardware validation)."""
        self.task: asyncio.Task[None] | None = None


class RuntimeSupervisor:
    """Per-camera command queue + serialized dispatcher for AI enable/disable."""

    def __init__(
        self,
        pipeline: PipelineHandle,
        bridge: AsyncBridge,
        admission: GpuAdmissionHook,
        *,
        on_valve_changed: Callable[[uuid.UUID, bool], None] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._bridge = bridge
        self._admission = admission
        self._on_valve_changed = on_valve_changed
        """Optional, None-safe (same idiom as every other collaborator in
        this codebase) -- fires after a real valve mutation succeeds,
        with the new ``drop`` state. Not a new AI policy: this changes
        nothing about whether/when AI is enabled -- it is an additional
        side effect at the one existing point every valve mutation
        already funnels through, letting Live Monitoring's WebRTC branch
        (apps/deepstream/app/live_stream/) switch which input feeds its
        encoder without owning or re-deciding any part of AI eligibility
        itself."""
        self._workers: dict[uuid.UUID, _CameraWorker] = {}
        self._valve_transition_count = 0
        self._runtime_error_count = 0
        self._last_command_latency_ms: float | None = None
        """RM-12 Camera Runtime Step 5 (Telemetry) instrumentation --
        counters/timing only, read via the properties below. Never read by
        this class's own control flow (idempotency/admission/ordering
        decisions are all unaffected by these values) -- purely additive,
        matching HeartbeatRegistry/PerformanceInstrumentation's established
        "observational, non-invasive" pattern elsewhere in this codebase."""

    def _worker_for(self, camera_id: uuid.UUID) -> _CameraWorker:
        worker = self._workers.get(camera_id)
        if worker is None:
            worker = _CameraWorker()
            worker.task = asyncio.get_event_loop().create_task(
                self._run_worker(camera_id, worker), name=f"runtime-supervisor-{camera_id}"
            )
            self._workers[camera_id] = worker
        return worker

    async def enable_ai(self, camera_id: uuid.UUID) -> CommandOutcome:
        return await self._submit(camera_id, enable=True)

    async def disable_ai(self, camera_id: uuid.UUID) -> CommandOutcome:
        return await self._submit(camera_id, enable=False)

    async def _submit(self, camera_id: uuid.UUID, *, enable: bool) -> CommandOutcome:
        worker = self._worker_for(camera_id)
        future: asyncio.Future[CommandOutcome] = asyncio.get_event_loop().create_future()
        await worker.queue.put(_QueuedCommand(enable=enable, future=future))
        return await future

    async def _run_worker(self, camera_id: uuid.UUID, worker: _CameraWorker) -> None:
        while True:
            command = await worker.queue.get()
            started_at = time.monotonic()
            try:
                outcome = await self._execute(camera_id, worker, command.enable)
            except asyncio.CancelledError:
                # This worker's own task was cancelled (remove_camera(), when
                # the camera is torn down mid-command) -- not a request from
                # whoever is awaiting command.future (e.g. DesiredStateSynchronizer,
                # a completely different task). Cancelling that future would
                # deliver asyncio.CancelledError to that unrelated awaiter,
                # which -- being a BaseException -- passes straight through
                # its own `except Exception` handling and gets misread as a
                # request to cancel *that* task too (hardware-confirmed: this
                # silently killed DesiredStateSynchronizer's forever-loop when
                # a camera's first AI command raced its own connection
                # failure). Setting an exception instead delivers a normal,
                # catchable failure -- the awaiter learns the command didn't
                # complete without being told it was itself cancelled.
                if not command.future.done():
                    command.future.set_exception(
                        RuntimeSupervisorError(
                            f"Camera {camera_id} was removed while this command was in flight"
                        )
                    )
                raise
            except Exception as exc:  # noqa: BLE001 -- propagated to the caller's future
                self._runtime_error_count += 1
                if not command.future.done():
                    command.future.set_exception(exc)
            else:
                if not command.future.done():
                    command.future.set_result(outcome)
            finally:
                self._last_command_latency_ms = (time.monotonic() - started_at) * 1000
                worker.queue.task_done()

    async def _execute(
        self, camera_id: uuid.UUID, worker: _CameraWorker, enable: bool
    ) -> CommandOutcome:
        if enable:
            if worker.ai_enabled is True:
                return CommandOutcome(accepted=True, reason="already enabled")
            # False or unknown (None, this worker's first command -- the
            # real valve's actual state has never been converged by this
            # supervisor yet) both require an actual mutation.
            if not self._admission.try_admit(camera_id):
                return CommandOutcome(accepted=False, reason="GPU admission rejected")
            try:
                await self._set_valve(camera_id, drop=False)
            except Exception:
                self._admission.release(camera_id)
                raise
            worker.ai_enabled = True
            return CommandOutcome(accepted=True)

        # DisableAI always succeeds (per Step 3's behavioral requirements).
        if worker.ai_enabled is False:
            return CommandOutcome(accepted=True, reason="already disabled")
        # True or unknown (None) both require an actual mutation -- a fresh
        # worker's unknown state must never be misread as "already
        # disabled" against a valve that actually starts open.
        await self._set_valve(camera_id, drop=True)
        worker.ai_enabled = False
        self._admission.release(camera_id)
        return CommandOutcome(accepted=True)

    async def _set_valve(self, camera_id: uuid.UUID, *, drop: bool) -> None:
        bin_ = self._pipeline.bin_for(camera_id)
        if bin_ is None:
            raise RuntimeSupervisorError(f"No active source bin for camera {camera_id}")

        def _mutate() -> None:
            valve = bin_.get_by_name(valve_element_name(camera_id))
            if valve is None:
                raise RuntimeSupervisorError(f"Valve element not found for camera {camera_id}")
            valve.set_property("drop", drop)
            if self._on_valve_changed is not None:
                self._on_valve_changed(camera_id, not drop)

        future = self._bridge.schedule_on_mainloop(_mutate)
        await asyncio.wrap_future(future)
        self._valve_transition_count += 1

    # -- RM-12 Camera Runtime Step 5 (Telemetry): read-only accessors only,
    # below this point. Every one of these reports on state this class
    # already owns for its own reasons -- none of them exist to feed a new
    # decision back into RuntimeSupervisor itself.

    def worker_camera_ids(self) -> frozenset[uuid.UUID]:
        """Every camera this supervisor has ever handled a command for."""
        return frozenset(self._workers.keys())

    def ai_enabled_camera_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(
            camera_id for camera_id, worker in self._workers.items() if worker.ai_enabled is True
        )

    def queued_command_count(self) -> int:
        """Total commands currently waiting across every camera's queue
        (excludes whichever single command each worker is actively
        executing, if any)."""
        return sum(worker.queue.qsize() for worker in self._workers.values())

    def all_workers_alive(self) -> bool:
        """True if no worker task has crashed or exited unexpectedly.
        Vacuously true with zero workers -- "no workers yet" is not the same
        condition as "a worker died"."""
        return all(
            worker.task is not None and not worker.task.done() for worker in self._workers.values()
        )

    @property
    def valve_transition_count(self) -> int:
        """Cumulative count of real valve mutations (both directions) since
        construction -- excludes idempotent no-ops."""
        return self._valve_transition_count

    @property
    def runtime_error_count(self) -> int:
        """Cumulative count of commands that raised (e.g. no active source
        bin) rather than resolving to a ``CommandOutcome``."""
        return self._runtime_error_count

    @property
    def last_command_latency_ms(self) -> float | None:
        """Wall-clock duration of the most recently completed command
        (``enable_ai``/``disable_ai``, whether it mutated the valve or was
        an idempotent no-op) -- ``None`` until at least one command has
        completed."""
        return self._last_command_latency_ms

    async def remove_camera(self, camera_id: uuid.UUID) -> None:
        """Completely destroys this one camera's worker (task, queue, and
        GPU-admission slot if held) -- the per-camera counterpart to
        ``stop()``. Root-cause fix (Operator Acceptance Testing ownership
        audit, 2026-08-03): before this method existed, nothing ever
        called it -- a deleted camera's worker task sat forever, blocked
        on its own empty queue, with its ``_workers`` entry never
        removed. Harmless in isolation (a different camera_id after
        re-registration never routes to the stale worker), but a genuine
        unbounded leak: every operator delete/re-register cycle over a
        long-running production process's life added one permanent,
        never-reclaimed entry. Idempotent (a camera with no worker at all
        is a no-op) and safe to call for a camera whose AI was never
        enabled/disabled even once (worker may not exist yet)."""
        worker = self._workers.pop(camera_id, None)
        if worker is None:
            return
        if worker.ai_enabled is True:
            self._admission.release(camera_id)
        if worker.task is not None:
            worker.task.cancel()
            try:
                await worker.task
            except asyncio.CancelledError:
                pass
        while not worker.queue.empty():
            pending = worker.queue.get_nowait()
            # set_exception, not cancel() -- same reasoning as _run_worker's
            # own CancelledError handler above: whoever is awaiting this
            # future is a different task than this one, and .cancel() would
            # incorrectly read to them as a request to cancel themselves.
            if not pending.future.done():
                pending.future.set_exception(
                    RuntimeSupervisorError(
                        f"Camera {camera_id} was removed while this command was still queued"
                    )
                )
            worker.queue.task_done()

    async def stop(self) -> None:
        """Cancels every camera's worker task and rejects any command still
        queued or in flight with a deterministic ``RuntimeSupervisorError``
        on its future (not ``CancelledError`` -- see ``_run_worker``'s own
        comment: the caller awaiting that future is a different task than
        this one, and delivering it a raw ``CancelledError`` risks being
        misread as a request to cancel that task too), rather than leaving
        a caller awaiting a future that would otherwise never resolve."""
        for worker in self._workers.values():
            if worker.task is not None:
                worker.task.cancel()
        for worker in self._workers.values():
            if worker.task is not None:
                try:
                    await worker.task
                except asyncio.CancelledError:
                    pass
            while not worker.queue.empty():
                pending = worker.queue.get_nowait()
                if not pending.future.done():
                    pending.future.set_exception(
                        RuntimeSupervisorError("RuntimeSupervisor is stopping")
                    )
                worker.queue.task_done()
        self._workers.clear()
