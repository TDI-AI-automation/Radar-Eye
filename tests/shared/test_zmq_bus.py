"""Tests for shared.events.zmq_bus -- the production cross-process
EventBus (ADR-029 Phase 4). Runs a real broker (in-process thread) and
real ZMQ sockets, no mocks, matching this repo's existing infra-test
convention (e.g. tests/shared/test_webrtc.py).
"""

from __future__ import annotations

import asyncio
import threading
import uuid

import pytest
import zmq

from shared.events.broker import run_broker
from shared.events.envelope import EventEnvelope
from shared.events.payloads import CameraDisconnectedPayload, SystemEventPayload
from shared.events.types import CameraDisconnectedEvent, SystemEvent
from shared.events.zmq_bus import ZmqEventBus


@pytest.fixture
def broker_ports() -> tuple[str, int, int]:
    """A fresh host/port pair per test, so parallel test runs (and the
    real production broker, if one happens to be running) never collide."""
    context = zmq.Context()
    probe_a = context.socket(zmq.PUSH)
    probe_a.bind("tcp://127.0.0.1:0")
    publish_port = int(probe_a.getsockopt_string(zmq.LAST_ENDPOINT).rsplit(":", 1)[1])
    probe_b = context.socket(zmq.PUSH)
    probe_b.bind("tcp://127.0.0.1:0")
    subscribe_port = int(probe_b.getsockopt_string(zmq.LAST_ENDPOINT).rsplit(":", 1)[1])
    probe_a.close()
    probe_b.close()
    context.term()
    return "127.0.0.1", publish_port, subscribe_port


@pytest.fixture
def running_broker(broker_ports: tuple[str, int, int]):
    host, publish_port, subscribe_port = broker_ports
    thread = threading.Thread(
        target=run_broker,
        kwargs={"host": host, "publish_port": publish_port, "subscribe_port": subscribe_port},
        daemon=True,
    )
    thread.start()
    yield host, publish_port, subscribe_port


def _make_bus(broker: tuple[str, int, int], *, source: str) -> ZmqEventBus:
    host, publish_port, subscribe_port = broker
    return ZmqEventBus(
        source=source,
        host=host,
        publish_port=publish_port,
        subscribe_port=subscribe_port,
        subscribe_settle_seconds=0.05,
        publish_timeout_seconds=0.2,
    )


def _camera_disconnected(camera_id, reason: str) -> CameraDisconnectedEvent:
    return CameraDisconnectedEvent(
        event_type="CameraDisconnectedEvent",
        source="test",
        payload=CameraDisconnectedPayload(camera_id=camera_id, reason=reason),
    )


@pytest.mark.asyncio
async def test_publish_reaches_a_real_subscriber(running_broker) -> None:
    publisher = _make_bus(running_broker, source="publisher")
    subscriber_bus = _make_bus(running_broker, source="subscriber")
    received: list[EventEnvelope] = []

    async def _handler(event: EventEnvelope) -> None:
        received.append(event)

    subscriber_bus.subscribe("CameraDisconnectedEvent", _handler)
    await asyncio.sleep(0.3)  # let the subscription settle past SUBSCRIBE_SETTLE_SECONDS

    camera_id = uuid.uuid4()
    await publisher.publish(_camera_disconnected(camera_id, "test-reason"))
    await asyncio.wait_for(_wait_for(received, 1), timeout=2.0)

    assert len(received) == 1
    assert received[0].payload.camera_id == camera_id
    assert received[0].payload.reason == "test-reason"

    await publisher.stop()
    await subscriber_bus.stop()


@pytest.mark.asyncio
async def test_topic_filtering_never_crosses_event_types(running_broker) -> None:
    publisher = _make_bus(running_broker, source="publisher")
    subscriber_bus = _make_bus(running_broker, source="subscriber")
    received: list[EventEnvelope] = []

    async def _handler(event: EventEnvelope) -> None:
        received.append(event)

    subscriber_bus.subscribe("CameraDisconnectedEvent", _handler)
    await asyncio.sleep(0.3)

    system_event = SystemEvent(
        event_type="SystemEvent",
        source="test",
        payload=SystemEventPayload(severity="INFO", source_component="test", message="hi"),
    )
    await publisher.publish(system_event)
    await publisher.publish(_camera_disconnected(uuid.uuid4(), "reason"))
    await asyncio.wait_for(_wait_for(received, 1), timeout=2.0)

    # Give any (incorrect) cross-delivery of the SystemEvent a moment to arrive.
    await asyncio.sleep(0.2)
    assert len(received) == 1
    assert received[0].event_type == "CameraDisconnectedEvent"

    await publisher.stop()
    await subscriber_bus.stop()


@pytest.mark.asyncio
async def test_drop_on_full_queue_emits_critical_system_event(running_broker) -> None:
    publisher = _make_bus(running_broker, source="publisher")
    subscriber_bus = _make_bus(running_broker, source="subscriber")
    subscriber_bus._queue_maxsize = 1  # noqa: SLF001 -- force a full queue deterministically

    released = asyncio.Event()

    async def _slow_handler(_event: EventEnvelope) -> None:
        await released.wait()

    system_events: list[EventEnvelope] = []

    async def _system_handler(event: EventEnvelope) -> None:
        system_events.append(event)

    subscriber_bus.subscribe("CameraDisconnectedEvent", _slow_handler, name="slow")
    subscriber_bus.subscribe("SystemEvent", _system_handler, name="system")
    await asyncio.sleep(0.3)

    camera_id = uuid.uuid4()
    for _ in range(4):
        await publisher.publish(_camera_disconnected(camera_id, "reason"))

    await asyncio.wait_for(_wait_for(system_events, 1), timeout=2.0)
    assert system_events[0].event_type == "SystemEvent"
    assert system_events[0].payload.severity == "CRITICAL"

    released.set()
    await publisher.stop()
    await subscriber_bus.stop()


async def _wait_for(collection: list, minimum: int) -> None:
    while len(collection) < minimum:
        await asyncio.sleep(0.05)
