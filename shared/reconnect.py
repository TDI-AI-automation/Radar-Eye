"""Reconnect backoff policy.

Promoted from ``apps/deepstream/app/ingestion/reconnect.py`` (Media
Architecture Reset, ADR-028) -- pure computation, zero GStreamer/asyncio/
transport dependency, so every process that owns a retry-capable
connection (Camera Ingestion's real RTSP session; Live Streaming/AI
Streaming/Recording's local subscription to Camera Ingestion or AI
Runtime) can reuse the identical policy rather than reinventing backoff
math per process. One camera's (or one subsystem's) failure must never
affect another's -- callers own one ``ReconnectPolicy`` instance per
thing being reconnected, never shared/global backoff state.
"""

from __future__ import annotations

from dataclasses import dataclass


def compute_backoff_seconds(
    attempt: int,
    *,
    initial_seconds: float,
    max_seconds: float,
    multiplier: float,
) -> float:
    """Delay before reconnect attempt number ``attempt`` (0-indexed).

    attempt=0 -> initial_seconds; each subsequent attempt multiplies by
    ``multiplier``, capped at ``max_seconds``.
    """
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    delay = initial_seconds * (multiplier**attempt)
    return min(delay, max_seconds)


@dataclass
class ReconnectPolicy:
    """Per-connection reconnect attempt counter and backoff delay."""

    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    multiplier: float = 2.0
    _attempt: int = 0

    def next_delay_seconds(self) -> float:
        """Delay to wait before the next reconnect attempt, then advance state."""
        delay = compute_backoff_seconds(
            self._attempt,
            initial_seconds=self.initial_backoff_seconds,
            max_seconds=self.max_backoff_seconds,
            multiplier=self.multiplier,
        )
        self._attempt += 1
        return delay

    def reset(self) -> None:
        """Call once a reconnect succeeds -- restarts backoff from the initial delay."""
        self._attempt = 0

    @property
    def attempt_count(self) -> int:
        return self._attempt
