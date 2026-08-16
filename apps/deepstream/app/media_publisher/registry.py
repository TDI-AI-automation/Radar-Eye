"""Thread-safe per-camera consumer registry -- RM-12 Camera Runtime Step 7.

``dispatch()`` runs from a GStreamer pad-probe callback, on whichever
streaming thread owns the buffer -- the exact same cross-thread contract as
``HeartbeatRegistry`` (``heartbeat_registry.py``), which this class
deliberately mirrors: a ``threading.Lock``-guarded dict, mutated by
``register``/``unregister`` (called from the asyncio side) and read by
``dispatch`` (called from a streaming thread).

Failure isolation lives here, not in each tier's probe callback: a
consumer that raises is logged and skipped -- it never stops delivery to
other consumers of the same camera, and it never propagates back into the
GStreamer probe (which would risk taking inference down with it).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

ConsumerT = TypeVar("ConsumerT")


class ConsumerRegistry(Generic[ConsumerT]):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumers: dict[uuid.UUID, list[ConsumerT]] = {}
        self._failure_counts: dict[int, int] = {}
        """Keyed by ``id(consumer)`` -- diagnostic only (see
        ``failure_count``); reset when a consumer is unregistered so a
        later, unrelated object that happens to reuse the same id starts
        clean."""

    def register(self, camera_id: uuid.UUID, consumer: ConsumerT) -> None:
        with self._lock:
            self._consumers.setdefault(camera_id, []).append(consumer)

    def unregister(self, camera_id: uuid.UUID, consumer: ConsumerT) -> None:
        with self._lock:
            consumers = self._consumers.get(camera_id)
            if consumers is not None and consumer in consumers:
                consumers.remove(consumer)
                if not consumers:
                    del self._consumers[camera_id]
            self._failure_counts.pop(id(consumer), None)

    def consumers_for(self, camera_id: uuid.UUID) -> list[ConsumerT]:
        with self._lock:
            return list(self._consumers.get(camera_id, ()))

    def failure_count(self, consumer: ConsumerT) -> int:
        with self._lock:
            return self._failure_counts.get(id(consumer), 0)

    def dispatch(self, camera_id: uuid.UUID, deliver: Callable[[ConsumerT], None]) -> None:
        """Call ``deliver(consumer)`` for every consumer currently
        registered for ``camera_id``, isolating failures. Safe to call with
        zero registered consumers (a no-op) -- the physical probe this
        feeds can exist and fire before any consumer has registered."""
        for consumer in self.consumers_for(camera_id):
            try:
                deliver(consumer)
            except Exception:  # noqa: BLE001 -- one failing consumer must never affect others
                logger.exception(
                    "Media Publisher consumer failed for camera %s -- isolated", camera_id
                )
                with self._lock:
                    self._failure_counts[id(consumer)] = (
                        self._failure_counts.get(id(consumer), 0) + 1
                    )
