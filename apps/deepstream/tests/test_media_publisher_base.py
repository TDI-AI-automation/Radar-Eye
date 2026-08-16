"""Tests for apps.deepstream.app.media_publisher.base._TieredPublisher --
RM-12 Camera Runtime Step 7.

Pure asyncio -- no DeepStream SDK. A concrete test subclass supplies fake
pads (plain Python objects recording add_probe/remove_probe calls) so the
shared attach/detach/register/unregister/shutdown lifecycle is exercised
without any real Gst object.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from apps.deepstream.app.media_publisher.base import MediaPublisherError, _TieredPublisher


class FakePad:
    def __init__(self) -> None:
        self.probes: dict[int, Callable[..., Any]] = {}
        self._next_id = 1

    def add_probe(self, _probe_type: Any, callback: Callable[..., Any], _user_data: Any) -> int:
        probe_id = self._next_id
        self._next_id += 1
        self.probes[probe_id] = callback
        return probe_id

    def remove_probe(self, probe_id: int) -> None:
        self.probes.pop(probe_id, None)


class RecordingPublisher(_TieredPublisher[Any]):
    """Concrete _TieredPublisher: pads keyed by camera_id in a plain dict,
    ``_deliver`` just calls the consumer directly with (camera_id, buffer)."""

    def __init__(self, bridge: Any, pads: dict[uuid.UUID, FakePad]) -> None:
        super().__init__(bridge)
        self._pads = pads

    def _find_pad(self, camera_id: uuid.UUID) -> FakePad | None:
        return self._pads.get(camera_id)

    def _deliver(self, consumer: Any, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        consumer(camera_id, gst_buffer)


@pytest.fixture
def bridge_and_publisher():
    import concurrent.futures

    class RealFutureBridge:
        def schedule_on_mainloop(self, func: Callable[[], Any]) -> concurrent.futures.Future:
            future: concurrent.futures.Future = concurrent.futures.Future()
            try:
                future.set_result(func())
            except (
                Exception
            ) as exc:  # noqa: BLE001 -- propagate to the future, matching AsyncBridge
                future.set_exception(exc)
            return future

    pads: dict[uuid.UUID, FakePad] = {}
    publisher = RecordingPublisher(RealFutureBridge(), pads)
    return publisher, pads


@pytest.mark.asyncio
class TestAttachDetach:
    async def test_attach_adds_exactly_one_probe(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pad = FakePad()
        pads[camera_id] = pad

        await publisher.attach(camera_id)

        assert len(pad.probes) == 1
        assert publisher.is_attached(camera_id)

    async def test_attach_is_idempotent(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pad = FakePad()
        pads[camera_id] = pad

        await publisher.attach(camera_id)
        await publisher.attach(camera_id)

        assert len(pad.probes) == 1  # not two

    async def test_attach_raises_when_pad_does_not_exist(self, bridge_and_publisher) -> None:
        publisher, _pads = bridge_and_publisher
        with pytest.raises(MediaPublisherError):
            await publisher.attach(uuid.uuid4())

    async def test_detach_removes_the_probe(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pad = FakePad()
        pads[camera_id] = pad
        await publisher.attach(camera_id)

        await publisher.detach(camera_id)

        assert pad.probes == {}
        assert not publisher.is_attached(camera_id)

    async def test_detach_is_idempotent(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pads[camera_id] = FakePad()
        await publisher.attach(camera_id)

        await publisher.detach(camera_id)
        await publisher.detach(camera_id)  # must not raise

    async def test_detach_before_attach_is_a_no_op(self, bridge_and_publisher) -> None:
        publisher, _pads = bridge_and_publisher
        await publisher.detach(uuid.uuid4())  # must not raise


@pytest.mark.asyncio
class TestRegisterUnregister:
    async def test_register_before_attach_does_not_raise(self, bridge_and_publisher) -> None:
        publisher, _pads = bridge_and_publisher
        publisher.register(uuid.uuid4(), lambda cam, buf: None)  # must not raise

    async def test_delivery_after_attach_and_register(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pad = FakePad()
        pads[camera_id] = pad
        received = []
        publisher.register(camera_id, lambda cam, buf: received.append((cam, buf)))

        await publisher.attach(camera_id)
        probe_callback = next(iter(pad.probes.values()))

        class _Info:
            def get_buffer(self) -> str:
                return "the-buffer"

        probe_callback(pad, _Info(), camera_id)

        assert received == [(camera_id, "the-buffer")]

    async def test_unregister_stops_delivery(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_id = uuid.uuid4()
        pad = FakePad()
        pads[camera_id] = pad
        received = []

        def consumer(cam: uuid.UUID, buf: Any) -> None:
            received.append((cam, buf))

        publisher.register(camera_id, consumer)
        await publisher.attach(camera_id)
        publisher.unregister(camera_id, consumer)

        probe_callback = next(iter(pad.probes.values()))

        class _Info:
            def get_buffer(self) -> str:
                return "the-buffer"

        probe_callback(pad, _Info(), camera_id)

        assert received == []


@pytest.mark.asyncio
class TestShutdown:
    async def test_shutdown_detaches_every_attached_camera(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pad_a, pad_b = FakePad(), FakePad()
        pads[camera_a] = pad_a
        pads[camera_b] = pad_b
        await publisher.attach(camera_a)
        await publisher.attach(camera_b)

        await publisher.shutdown()

        assert pad_a.probes == {}
        assert pad_b.probes == {}
        assert not publisher.is_attached(camera_a)
        assert not publisher.is_attached(camera_b)

    async def test_shutdown_with_nothing_attached_is_a_no_op(self, bridge_and_publisher) -> None:
        publisher, _pads = bridge_and_publisher
        await publisher.shutdown()  # must not raise


@pytest.mark.asyncio
class TestConcurrentCamerasDoNotInterfere:
    async def test_attaching_one_camera_does_not_affect_another(self, bridge_and_publisher) -> None:
        publisher, pads = bridge_and_publisher
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        pads[camera_a] = FakePad()
        # camera_b intentionally has no pad -- attach() for it must fail
        # independently of camera_a's success.
        await publisher.attach(camera_a)

        with pytest.raises(MediaPublisherError):
            await publisher.attach(camera_b)

        assert publisher.is_attached(camera_a)
        assert not publisher.is_attached(camera_b)
