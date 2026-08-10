"""Unified heartbeat registry -- RM-11.SIV.

Source: RM-11.SIV Principal Engineer approval, "Additional Requirement --
Unified Heartbeat": every subsystem exposes one ``HeartbeatStatus`` object,
and both the validation dashboard and the watchdog must read from the exact
same registry -- one source of truth, not two independently-timestamped
tracking schemes.

Deliberately as dependency-free as ``instrumentation.py`` (no ``pyds``/``gi``
import here) -- production modules record into it directly (this is
instrumentation, not business logic, per the SIV approval's "additive,
non-invasive" rule), while ``apps/deepstream/app/siv/watchdog.py`` and
``siv/dashboard.py`` only ever read from it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HeartbeatStatus:
    """One subsystem's current liveness, as of the last time it reported."""

    component: str
    last_seen_monotonic: float
    counter: int
    healthy: bool
    reason: str | None = None

    def age_seconds(self, *, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.last_seen_monotonic


@dataclass
class _ComponentState:
    counter: int = 0
    last_seen_monotonic: float = field(default_factory=time.monotonic)
    reason: str | None = None


class HeartbeatRegistry:
    """Thread-safe: recorded from GStreamer pad probes (streaming threads)
    and asyncio call sites alike; read from the watchdog's asyncio task and
    the dashboard's render loop.

    ``healthy`` is computed at read time against a per-component staleness
    threshold, not stored -- "healthy" is a function of *when* it's asked,
    not a fact recorded at write time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._components: dict[str, _ComponentState] = {}

    def beat(self, component: str, *, reason: str | None = None) -> None:
        """Record one unit of successful activity for ``component``. Cheap
        (a lock + dict write) -- safe to call at inference frame rate, same
        contract as ``PerformanceInstrumentation.record_frame``."""
        with self._lock:
            state = self._components.setdefault(component, _ComponentState())
            state.counter += 1
            state.last_seen_monotonic = time.monotonic()
            state.reason = reason

    def status(
        self, component: str, *, stale_after_seconds: float, now: float | None = None
    ) -> HeartbeatStatus:
        """Current status for one component. A component that has never
        called ``beat()`` is reported unhealthy with counter=0 rather than
        raising -- the watchdog must be able to ask about every configured
        component from startup, before the pipeline has produced anything."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            state = self._components.get(component)
        if state is None:
            return HeartbeatStatus(
                component=component,
                last_seen_monotonic=now,
                counter=0,
                healthy=False,
                reason="no activity recorded yet",
            )
        age = now - state.last_seen_monotonic
        healthy = age <= stale_after_seconds
        reason = (
            state.reason
            if healthy
            else f"stale for {age:.1f}s (threshold {stale_after_seconds:.1f}s)"
        )
        return HeartbeatStatus(
            component=component,
            last_seen_monotonic=state.last_seen_monotonic,
            counter=state.counter,
            healthy=healthy,
            reason=reason,
        )

    def known_components(self) -> list[str]:
        with self._lock:
            return list(self._components)
