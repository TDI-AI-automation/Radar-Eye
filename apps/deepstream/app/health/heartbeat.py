"""Per-camera FPS heartbeat reporting into RM-09's ``HealthCollector``.

Source: DEEPSTREAM_PIPELINE_SPEC.md's implied per-camera health surfacing
(FRONTEND_BACKEND_CONTRACTS.md's ``GET /cameras/{camera_id}/health`` and
``/ws/camera-health``, backed by RM-09's ``HealthCollector.
record_camera_heartbeat``). ``HealthCollector`` lives in ``apps.api`` and,
per the RM-11 design review's single-process decision, is reachable
in-process here -- no bus, no IPC.

Split in two pieces:
  - ``FrameCounter``: a thread-safe counter incremented from GStreamer pad
    probes (a different thread than this scheduler). Phase 0 counts frames
    post-decode, pre-inference (no PGIE/SGIE exist yet).
  - ``HeartbeatScheduler``: a plain asyncio periodic task that reads counts
    and calls ``HealthCollector.record_camera_heartbeat``. Runs on the
    application's asyncio loop directly -- it never touches GStreamer, so
    it does not need the AsyncBridge.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.api.app.health import HealthCollector
    from shared.schemas.camera import CameraConnectionStatus

logger = logging.getLogger(__name__)


class FrameCounter:
    """Thread-safe per-camera decoded-frame counter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[uuid.UUID, int] = {}

    def increment(self, camera_id: uuid.UUID) -> None:
        """Call from a GStreamer pad probe -- cheap, thread-safe."""
        with self._lock:
            self._counts[camera_id] = self._counts.get(camera_id, 0) + 1

    def snapshot_and_reset(self) -> dict[uuid.UUID, int]:
        with self._lock:
            counts = dict(self._counts)
            self._counts.clear()
        return counts


StatusProvider = Callable[[uuid.UUID], "CameraConnectionStatus"]


class HeartbeatScheduler:
    """Periodically reports each known camera's status/FPS to HealthCollector."""

    def __init__(
        self,
        *,
        health_collector: HealthCollector,
        frame_counter: FrameCounter,
        camera_ids: list[uuid.UUID],
        status_provider: StatusProvider,
        interval_seconds: float = 1.0,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self._health_collector = health_collector
        self._frame_counter = frame_counter
        self._camera_ids = camera_ids
        self._status_provider = status_provider
        self._interval_seconds = interval_seconds
        self._on_tick = on_tick
        """RM-11.SIV: optional hook, called at the end of every tick() --
        lets runtime.py record a "heartbeat" liveness beat on the shared
        HeartbeatRegistry without this (RM-09) module needing to know that
        registry exists."""
        self._task: asyncio.Task[None] | None = None

    def tick(self) -> None:
        """Report one round of heartbeats for every known camera. Public
        (rather than private) specifically so tests can call it directly
        without waiting on the real interval."""
        counts = self._frame_counter.snapshot_and_reset()
        now = datetime.now(timezone.utc)
        for camera_id in self._camera_ids:
            status = self._status_provider(camera_id)
            frame_count = counts.get(camera_id, 0)
            fps = frame_count / self._interval_seconds if status == "CONNECTED" else None
            self._health_collector.record_camera_heartbeat(
                camera_id, status=status, fps=fps, timestamp=now
            )
        if self._on_tick is not None:
            self._on_tick()

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval_seconds)
                try:
                    self.tick()
                except Exception:
                    logger.exception("HeartbeatScheduler.tick() failed")
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("HeartbeatScheduler is already started")
        self._task = asyncio.get_event_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
