"""Internal event bus -- the producer -> event -> consumer transport (ADR-007).

Source: docs/EVENT_CONTRACTS.md ("Event Transport Rules", "Event Versioning"),
docs/DEEPSTREAM_PIPELINE_SPEC.md ("Stage 10: Event Bus", "Event Bus Failure").
Authority: RM-04 design review.

``EventBus`` is an abstract transport contract; ``InProcessEventBus`` is the
initial concrete implementation (single-process, in-memory). Producers and
consumers depend only on ``EventBus``, so a future distributed implementation
(for multi-node deployments, per CLAUDE.md's Scalability section) can replace
it without changing any producer or consumer code -- the same abstraction
pattern used for ``CredentialEncryptionProvider`` (RM-03).

Design summary (see RM-04 design review for full rationale):
  - Delivery: best-effort, at-most-once per subscriber. No durable log backs
    this -- a subscriber that is down when an event publishes simply misses
    it. Acceptable for a single-node, modest-volume transport (only debounced
    state-change events reach the bus, never per-frame data -- ADR-008).
  - Ordering: FIFO per producer per event type only. No cross-producer or
    cross-event-type ordering guarantee. Consumers needing strict ordering
    across producers must sort by the envelope's ``timestamp`` (INV-014).
  - Back-pressure: each subscriber has its own bounded queue and a dedicated
    background task. ``publish()`` waits up to ``publish_timeout_seconds``
    for space in a full subscriber queue; if it doesn't clear in time, the
    event is dropped for that subscriber only (others are unaffected, and
    the publish call never fails because of one slow consumer) and a
    CRITICAL SystemEvent is emitted so the condition is operator-visible.
  - Replay: none. The bus holds no durable event log; a consumer needing
    current state reconstructs it from the database (ADR-008), not by
    replaying past events.
  - Non-goals (explicitly out of scope, per the approved RM-04 policy):
    dynamic queue resizing, priority queues, dead-letter queues, replay
    mechanisms, subscriber eviction.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from shared.events.envelope import EventEnvelope
from shared.events.payloads import SystemEventPayload
from shared.events.types import SystemEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]

DEFAULT_QUEUE_MAXSIZE = 1000
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 1.0


class EventBus(ABC):
    """Transport contract: producers publish, consumers subscribe."""

    @abstractmethod
    async def publish(self, event: EventEnvelope) -> None:
        """Deliver ``event`` to every subscriber registered for its event type."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler, *, name: str | None = None) -> None:
        """Register ``handler`` to receive every event of ``event_type``."""

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Stop delivering ``event_type`` events to ``handler``."""


class _Subscriber:
    """A single subscriber's queue and background delivery task.

    Internal to InProcessEventBus -- always constructed and immediately
    running inside an active event loop (subscribe() is only ever called
    from async contexts).
    """

    def __init__(self, name: str, handler: EventHandler, queue_maxsize: int) -> None:
        self.name = name
        self.handler = handler
        self.queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=queue_maxsize)
        self.drop_count = 0
        self._task: asyncio.Task[None] = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                await self.handler(event)
            except Exception:
                logger.exception(
                    "Subscriber '%s' raised while handling %s (event_id=%s)",
                    self.name,
                    event.event_type,
                    event.event_id,
                )


class InProcessEventBus(EventBus):
    """Async, in-process pub/sub. See module docstring for the full design."""

    def __init__(
        self,
        *,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        publish_timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        source: str = "event_bus",
    ) -> None:
        self._subscribers: dict[str, list[_Subscriber]] = {}
        self._queue_maxsize = queue_maxsize
        self._publish_timeout_seconds = publish_timeout_seconds
        self._source = source

    def subscribe(self, event_type: str, handler: EventHandler, *, name: str | None = None) -> None:
        subscriber = _Subscriber(
            name=name or str(getattr(handler, "__qualname__", repr(handler))),
            handler=handler,
            queue_maxsize=self._queue_maxsize,
        )
        self._subscribers.setdefault(event_type, []).append(subscriber)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        subscribers = self._subscribers.get(event_type, [])
        for subscriber in list(subscribers):
            if subscriber.handler is handler:
                subscribers.remove(subscriber)
                await subscriber.stop()

    async def publish(self, event: EventEnvelope) -> None:
        for subscriber in list(self._subscribers.get(event.event_type, [])):
            try:
                await asyncio.wait_for(
                    subscriber.queue.put(event), timeout=self._publish_timeout_seconds
                )
            except asyncio.TimeoutError:
                subscriber.drop_count += 1
                await self._emit_drop_alert(subscriber, event)

    async def stop(self) -> None:
        """Cancel every subscriber's background task (test/shutdown helper)."""
        for subscribers in self._subscribers.values():
            for subscriber in subscribers:
                await subscriber.stop()

    async def _emit_drop_alert(self, subscriber: _Subscriber, event: EventEnvelope) -> None:
        message = (
            f"Subscriber '{subscriber.name}' queue full after "
            f"{self._publish_timeout_seconds}s -- dropped {event.event_type} "
            f"(event_id={event.event_id}). queue_depth={subscriber.queue.qsize()} "
            f"drop_count={subscriber.drop_count}"
        )
        # Always logged directly first: guaranteed visibility even if
        # SystemEvent's own subscribers are also backed up.
        logger.critical(message)

        alert = SystemEvent(
            event_type="SystemEvent",
            source=self._source,
            payload=SystemEventPayload(
                severity="CRITICAL",
                source_component=self._source,
                message=message,
            ),
        )
        for alert_subscriber in self._subscribers.get("SystemEvent", []):
            if alert_subscriber is subscriber:
                continue  # don't re-target the queue that just overflowed
            try:
                alert_subscriber.queue.put_nowait(alert)
            except asyncio.QueueFull:
                pass  # already logged critically above; don't cascade
