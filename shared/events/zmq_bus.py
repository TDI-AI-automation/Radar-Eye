"""Production EventBus transport -- ADR-029 Phase 4.

``ZmqEventBus`` is the cross-process ``EventBus`` implementation: every
publisher connects a PUB socket, every subscriber connects a SUB socket,
both to the single ``shared.events.broker`` process (see that module's
docstring) -- neither side ever needs the other's address. All
(de)serialization happens here, never in the broker.

Reuses ``bus.py``'s ``_Subscriber`` verbatim for the actual queue/dispatch/
fault-isolation loop, so per-subscriber isolation and the drop-on-full-
queue -> CRITICAL ``SystemEvent`` behavior are identical to
``InProcessEventBus`` -- this class only adds the network transport
underneath the same contract.

The PUB socket (and any SUB sockets from ``subscribe()``) are created
lazily, on first actual ``publish()``/``subscribe()`` call, not in
``__init__``. ``InProcessEventBus`` is pure Python objects, so
constructing one and never using it was always harmless; a real socket is
not. Callers that construct a bus as part of building an application
object (``create_app()``) but then never exercise it in a given code path
(e.g. a test that only inspects the app's routes/schema, or drives it
through a transport that never runs its ASGI lifespan) must not pay for
or leak a socket they never used.

The ``zmq.asyncio.Context`` itself is a **process-wide singleton**
(``_shared_context()``), not one per ``ZmqEventBus`` instance -- this is
the standard ZMQ usage pattern (one context per process, many sockets),
and it is required here, not just idiomatic: a ``zmq.asyncio.Context`` is
bound to the asyncio event loop it was created in, and pytest-asyncio
gives every test function its own loop. A per-instance context that
outlives its creating test (nothing calls ``stop()`` on a bus built via a
transport that never runs the ASGI lifespan -- true of most
``httpx.ASGITransport``-based router tests) gets garbage-collected later,
often inside a *different* test's event loop or after its own loop has
already closed. ``Context.__del__`` calls the blocking, synchronous
``Context.term()`` -- confirmed directly, via a real hang reproduced on
real hardware: ``term()`` never returned, freezing the entire test
process mid-``Base.metadata.create_all()`` in a completely unrelated
test, until the run was killed. A shared, process-wide context is never
garbage-collected mid-session (a module-level reference keeps it alive),
so this specific hang class cannot occur; it is only ever torn down at
interpreter exit, the one place synchronous, cross-loop cleanup is
actually safe.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import zmq
import zmq.asyncio

from shared.events.bus import (
    DEFAULT_PUBLISH_TIMEOUT_SECONDS,
    DEFAULT_QUEUE_MAXSIZE,
    EventBus,
    EventHandler,
    _Subscriber,
)
from shared.events.config import EVENT_BUS_HOST, EVENT_BUS_PUBLISH_PORT, EVENT_BUS_SUBSCRIBE_PORT
from shared.events.envelope import EventEnvelope
from shared.events.payloads import SystemEventPayload
from shared.events.registry import EVENT_CLASS_BY_TYPE
from shared.events.types import SystemEvent

logger = logging.getLogger(__name__)

SUBSCRIBE_SETTLE_SECONDS = 0.2
"""One-time, startup-only delay covering PUB/SUB's well-known slow-joiner
window (a fresh socket takes a brief moment for the broker to register
before it reliably sends/receives). Applied exactly once per socket: a
subscriber's pump task waits it out before starting its receive loop, and
a bus's PUB socket (created lazily, on its first ``publish()`` call) waits
it out right after connecting, before that first send. Never used again
after that for either socket -- delivery is immediate for every message
after this initial settle."""


@dataclass
class _Subscription:
    subscriber: _Subscriber
    socket: zmq.asyncio.Socket
    task: asyncio.Task[None]


_shared_context: zmq.asyncio.Context | None = None
"""Process-wide, one per interpreter -- see the module docstring for why
this must not be scoped per ``ZmqEventBus`` instance."""


def _get_shared_context() -> zmq.asyncio.Context:
    global _shared_context
    if _shared_context is None:
        context = zmq.asyncio.Context()
        # LINGER=0 on every socket this context creates: a PUB socket with
        # nothing subscribed (no broker in a test process) has
        # undeliverable messages queued forever otherwise, which blocks
        # that *socket's* close -- matches this bus's own already-approved
        # best-effort/at-most-once semantics (RM-04): an undeliverable
        # message should be dropped, never block anything, ever.
        context.setsockopt(zmq.LINGER, 0)
        _shared_context = context
    return _shared_context


class ZmqEventBus(EventBus):
    """Cross-process ``EventBus`` over a ZMQ XSUB/XPUB broker. See module
    docstring."""

    def __init__(
        self,
        *,
        source: str,
        host: str = EVENT_BUS_HOST,
        publish_port: int = EVENT_BUS_PUBLISH_PORT,
        subscribe_port: int = EVENT_BUS_SUBSCRIBE_PORT,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        publish_timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        subscribe_settle_seconds: float = SUBSCRIBE_SETTLE_SECONDS,
    ) -> None:
        self._source = source
        self._host = host
        self._publish_port = publish_port
        self._subscribe_port = subscribe_port
        self._queue_maxsize = queue_maxsize
        self._publish_timeout_seconds = publish_timeout_seconds
        self._subscribe_settle_seconds = subscribe_settle_seconds
        self._subscriptions: dict[str, list[_Subscription]] = {}

        self._pub_socket: zmq.asyncio.Socket | None = None

    async def _ensure_pub_socket(self) -> zmq.asyncio.Socket:
        """Lazily creates and connects the PUB socket, and -- only the
        first time, only for this one socket -- waits out the same
        slow-joiner settle window a fresh SUB subscription needs. Eager
        (``__init__``-time) connection used to give the socket this same
        head start for free, before any caller's first real publish;
        lazy creation means that head start has to happen here instead,
        exactly once, or a publish issued immediately after this socket's
        first connection can be silently dropped before the broker has
        finished registering it."""
        if self._pub_socket is None:
            pub_socket = _get_shared_context().socket(zmq.PUB)
            pub_socket.setsockopt(zmq.LINGER, 0)  # belt-and-suspenders; see _get_shared_context
            pub_socket.connect(f"tcp://{self._host}:{self._publish_port}")
            self._pub_socket = pub_socket
            await asyncio.sleep(self._subscribe_settle_seconds)
        return self._pub_socket

    async def publish(self, event: EventEnvelope) -> None:
        pub_socket = await self._ensure_pub_socket()
        await pub_socket.send_multipart(
            [event.event_type.encode(), event.model_dump_json().encode()]
        )

    def subscribe(self, event_type: str, handler: EventHandler, *, name: str | None = None) -> None:
        subscriber = _Subscriber(
            name=name or str(getattr(handler, "__qualname__", repr(handler))),
            handler=handler,
            queue_maxsize=self._queue_maxsize,
        )
        sub_socket = _get_shared_context().socket(zmq.SUB)
        sub_socket.setsockopt(zmq.LINGER, 0)  # belt-and-suspenders; see _get_shared_context
        sub_socket.connect(f"tcp://{self._host}:{self._subscribe_port}")
        sub_socket.setsockopt(zmq.SUBSCRIBE, event_type.encode())
        task = asyncio.create_task(self._pump(event_type, sub_socket, subscriber))
        self._subscriptions.setdefault(event_type, []).append(
            _Subscription(subscriber=subscriber, socket=sub_socket, task=task)
        )

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        subscriptions = self._subscriptions.get(event_type, [])
        for subscription in list(subscriptions):
            if subscription.subscriber.handler is not handler:
                continue
            subscriptions.remove(subscription)
            subscription.task.cancel()
            try:
                await subscription.task
            except asyncio.CancelledError:
                pass
            subscription.socket.close()
            await subscription.subscriber.stop()

    async def stop(self) -> None:
        """Tear down every subscription and close this instance's own PUB
        socket (test/shutdown helper, mirroring ``InProcessEventBus.stop()``).
        A bus that was constructed but never actually used (no lazy socket
        ever created) has nothing to close -- safe no-op. Never terminates
        the shared context -- see the module docstring; that is a
        process-wide resource other ``ZmqEventBus`` instances may still be
        using, torn down only at interpreter exit."""
        for event_type, subscriptions in list(self._subscriptions.items()):
            for subscription in list(subscriptions):
                await self.unsubscribe(event_type, subscription.subscriber.handler)
        if self._pub_socket is not None:
            self._pub_socket.close()
            self._pub_socket = None

    async def _pump(
        self, event_type: str, sub_socket: zmq.asyncio.Socket, subscriber: _Subscriber
    ) -> None:
        """Reads deserialized events off ``sub_socket`` and feeds
        ``subscriber``'s queue -- the same queue ``_Subscriber``'s own
        background dispatch task consumes, so handler dispatch/fault
        isolation is identical to ``InProcessEventBus``."""
        await asyncio.sleep(self._subscribe_settle_seconds)
        event_class = EVENT_CLASS_BY_TYPE[event_type]
        while True:
            _topic, raw = await sub_socket.recv_multipart()
            event = event_class.model_validate_json(raw)
            try:
                await asyncio.wait_for(
                    subscriber.queue.put(event), timeout=self._publish_timeout_seconds
                )
            except asyncio.TimeoutError:
                subscriber.drop_count += 1
                await self._emit_drop_alert(subscriber, event)

    async def _emit_drop_alert(self, subscriber: _Subscriber, event: EventEnvelope) -> None:
        message = (
            f"Subscriber '{subscriber.name}' queue full after "
            f"{self._publish_timeout_seconds}s -- dropped {event.event_type} "
            f"(event_id={event.event_id}). queue_depth={subscriber.queue.qsize()} "
            f"drop_count={subscriber.drop_count}"
        )
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
        for subscription in self._subscriptions.get("SystemEvent", []):
            if subscription.subscriber is subscriber:
                continue  # don't re-target the queue that just overflowed
            try:
                subscription.subscriber.queue.put_nowait(alert)
            except asyncio.QueueFull:
                pass  # already logged critically above; don't cascade
