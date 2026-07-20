"""Tests for shared.events.bus (RM-04 -- Internal Event Bus).

Source: docs/IMPLEMENTATION_ROADMAP.md's RM-04 acceptance/testing criteria
plus the design decisions from the RM-04 design review (delivery, ordering,
fault isolation, back-pressure).
"""

from __future__ import annotations

import asyncio
import logging

import pytest
import pytest_asyncio

from shared.events.bus import InProcessEventBus
from shared.events.payloads import SystemEventPayload
from shared.events.types import SystemEvent


@pytest_asyncio.fixture
async def bus():
    instance = InProcessEventBus(queue_maxsize=10, publish_timeout_seconds=0.2)
    yield instance
    await instance.stop()


def _system_event(message: str = "test") -> SystemEvent:
    return SystemEvent(
        event_type="SystemEvent",
        source="test",
        payload=SystemEventPayload(severity="INFO", source_component="test", message=message),
    )


def _collecting_handler(sink: asyncio.Queue):
    async def handler(event):
        await sink.put(event)

    return handler


@pytest.mark.asyncio
class TestDelivery:
    async def test_publish_delivers_to_single_subscriber(self, bus: InProcessEventBus) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(sink))

        event = _system_event("hello")
        await bus.publish(event)

        received = await asyncio.wait_for(sink.get(), timeout=1.0)
        assert received.event_id == event.event_id
        assert received.payload.message == "hello"

    async def test_publish_delivers_to_multiple_subscribers_of_same_event_type(
        self, bus: InProcessEventBus
    ) -> None:
        sink_a: asyncio.Queue = asyncio.Queue()
        sink_b: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(sink_a), name="A")
        bus.subscribe("SystemEvent", _collecting_handler(sink_b), name="B")

        event = _system_event("broadcast")
        await bus.publish(event)

        received_a = await asyncio.wait_for(sink_a.get(), timeout=1.0)
        received_b = await asyncio.wait_for(sink_b.get(), timeout=1.0)
        assert received_a.event_id == received_b.event_id == event.event_id

    async def test_subscribers_of_different_event_types_are_isolated(
        self, bus: InProcessEventBus
    ) -> None:
        system_sink: asyncio.Queue = asyncio.Queue()
        other_sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(system_sink))
        bus.subscribe("SomeOtherEvent", _collecting_handler(other_sink))

        await bus.publish(_system_event("only for SystemEvent subscribers"))

        await asyncio.wait_for(system_sink.get(), timeout=1.0)
        assert other_sink.empty()

    async def test_unsubscribe_stops_delivery(self, bus: InProcessEventBus) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        handler = _collecting_handler(sink)
        bus.subscribe("SystemEvent", handler)

        await bus.unsubscribe("SystemEvent", handler)
        await bus.publish(_system_event("should not arrive"))

        await asyncio.sleep(0.05)
        assert sink.empty()


@pytest.mark.asyncio
class TestOrdering:
    async def test_events_from_one_producer_arrive_in_order(self, bus: InProcessEventBus) -> None:
        sink: asyncio.Queue = asyncio.Queue()
        bus.subscribe("SystemEvent", _collecting_handler(sink))

        events = [_system_event(f"message-{i}") for i in range(10)]
        for event in events:
            await bus.publish(event)

        received = [await asyncio.wait_for(sink.get(), timeout=1.0) for _ in events]
        assert [e.payload.message for e in received] == [f"message-{i}" for i in range(10)]


@pytest.mark.asyncio
class TestFaultIsolation:
    """Roadmap acceptance criterion: kill one consumer, confirm others unaffected."""

    async def test_one_subscriber_raising_does_not_affect_others(
        self, bus: InProcessEventBus, caplog: pytest.LogCaptureFixture
    ) -> None:
        healthy_sink: asyncio.Queue = asyncio.Queue()

        async def failing_handler(event):
            raise RuntimeError("simulated consumer crash")

        bus.subscribe("SystemEvent", failing_handler, name="failing")
        bus.subscribe("SystemEvent", _collecting_handler(healthy_sink), name="healthy")

        with caplog.at_level(logging.ERROR):
            await bus.publish(_system_event("both should attempt delivery"))
            received = await asyncio.wait_for(healthy_sink.get(), timeout=1.0)

        assert received.payload.message == "both should attempt delivery"
        assert "failing" in caplog.text

    async def test_publish_does_not_raise_when_a_subscriber_fails(
        self, bus: InProcessEventBus
    ) -> None:
        async def failing_handler(event):
            raise RuntimeError("simulated consumer crash")

        bus.subscribe("SystemEvent", failing_handler)

        await bus.publish(_system_event("must not propagate"))  # no raise expected


@pytest.mark.asyncio
class TestBackPressure:
    async def test_slow_subscriber_drops_after_timeout_and_emits_critical_alert(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bus = InProcessEventBus(queue_maxsize=1, publish_timeout_seconds=0.05)
        try:
            never_returns = asyncio.Event()

            async def stuck_handler(event):
                await never_returns.wait()  # simulates a permanently stuck consumer

            alert_sink: asyncio.Queue = asyncio.Queue()
            bus.subscribe("SystemEvent", stuck_handler, name="stuck-consumer")
            bus.subscribe("SystemEvent", _collecting_handler(alert_sink), name="alert-listener")

            # First publish: the stuck handler immediately picks this one up,
            # queue is now empty again but the handler never completes.
            await bus.publish(_system_event("first"))
            await asyncio.sleep(0.05)

            # Second publish: fills the stuck subscriber's 1-slot queue.
            await bus.publish(_system_event("second"))

            # Third publish: stuck subscriber's queue is full and never
            # drains -- this should time out and drop, but must not raise,
            # and must not block the alert-listener subscriber.
            with caplog.at_level(logging.CRITICAL):
                await bus.publish(_system_event("third"))

            assert "queue full" in caplog.text.lower() or "dropped" in caplog.text.lower()

            # The healthy subscriber still received "first" and "second"
            # (strictly before anything related to the "third" publish call,
            # since those completed in full before "third" was published).
            first = await asyncio.wait_for(alert_sink.get(), timeout=1.0)
            second = await asyncio.wait_for(alert_sink.get(), timeout=1.0)
            assert [first.payload.message, second.payload.message] == ["first", "second"]

            # The "third" publish call delivers to both subscribers: the
            # stuck one times out (emitting a CRITICAL alert immediately,
            # since it's dispatched to first) and the healthy one still gets
            # "third" itself -- both end up in alert_sink, order between the
            # two not otherwise guaranteed.
            remaining = [await asyncio.wait_for(alert_sink.get(), timeout=1.0) for _ in range(2)]
            third = next(e for e in remaining if e.payload.message == "third")
            alert = next(e for e in remaining if e is not third)
            assert third.payload.message == "third"
            assert alert.payload.severity == "CRITICAL"
            assert "stuck-consumer" in alert.payload.message
        finally:
            await bus.stop()

    async def test_alert_delivery_itself_does_not_raise_when_every_subscriber_is_stuck(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Must not cascade: even if the alert's own targets are also
        backed up, publish() still returns normally."""
        bus = InProcessEventBus(queue_maxsize=1, publish_timeout_seconds=0.05)
        try:
            never_returns = asyncio.Event()

            async def stuck_handler(event):
                await never_returns.wait()

            bus.subscribe("SystemEvent", stuck_handler, name="stuck-a")
            bus.subscribe("SystemEvent", stuck_handler, name="stuck-b")

            await bus.publish(_system_event("first"))  # picked up immediately by both
            await asyncio.sleep(0.05)
            await bus.publish(_system_event("second"))  # fills both queues (maxsize=1)

            with caplog.at_level(logging.CRITICAL):
                await bus.publish(_system_event("third"))  # both time out; no raise expected

            assert caplog.text.lower().count("queue full") >= 2
        finally:
            await bus.stop()
