"""Tests for apps.deepstream.app.media_publisher.registry.ConsumerRegistry
-- RM-12 Camera Runtime Step 7.

Pure Python -- no DeepStream SDK, no asyncio needed (dispatch() is a plain
synchronous call, matching how it's actually invoked from a GStreamer pad
probe).
"""

from __future__ import annotations

import threading
import uuid

from apps.deepstream.app.media_publisher.registry import ConsumerRegistry


class _RecordingConsumer:
    def __init__(self, *, fail: bool = False) -> None:
        self.received: list[tuple[uuid.UUID, object]] = []
        self.fail = fail

    def __call__(self, camera_id: uuid.UUID, payload: object) -> None:
        if self.fail:
            raise RuntimeError("simulated consumer failure")
        self.received.append((camera_id, payload))


class TestRegisterUnregister:
    def test_register_then_dispatch_delivers_to_the_consumer(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        consumer = _RecordingConsumer()
        registry.register(camera_id, consumer)

        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))

        assert consumer.received == [(camera_id, "buf")]

    def test_dispatch_with_no_registered_consumers_is_a_no_op(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        registry.dispatch(uuid.uuid4(), lambda c: c(uuid.uuid4(), "buf"))  # must not raise

    def test_unregister_stops_delivery(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        consumer = _RecordingConsumer()
        registry.register(camera_id, consumer)
        registry.unregister(camera_id, consumer)

        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))

        assert consumer.received == []

    def test_unregister_unknown_consumer_does_not_raise(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        registry.unregister(uuid.uuid4(), _RecordingConsumer())  # must not raise

    def test_multiple_consumers_for_the_same_camera_all_receive(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        a, b = _RecordingConsumer(), _RecordingConsumer()
        registry.register(camera_id, a)
        registry.register(camera_id, b)

        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))

        assert a.received == [(camera_id, "buf")]
        assert b.received == [(camera_id, "buf")]

    def test_consumers_are_isolated_per_camera(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_a, camera_b = uuid.uuid4(), uuid.uuid4()
        consumer_a = _RecordingConsumer()
        registry.register(camera_a, consumer_a)

        registry.dispatch(camera_b, lambda c: c(camera_b, "buf"))

        assert consumer_a.received == []


class TestFailureIsolation:
    def test_a_failing_consumer_does_not_affect_others(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        failing = _RecordingConsumer(fail=True)
        healthy = _RecordingConsumer()
        registry.register(camera_id, failing)
        registry.register(camera_id, healthy)

        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))  # must not raise

        assert healthy.received == [(camera_id, "buf")]

    def test_failure_count_increments_on_each_failure(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        failing = _RecordingConsumer(fail=True)
        registry.register(camera_id, failing)

        assert registry.failure_count(failing) == 0
        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))
        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))

        assert registry.failure_count(failing) == 2

    def test_a_failing_consumer_stays_registered_after_failing(self) -> None:
        """Isolation means logged-and-skipped, not permanently removed --
        a transient failure must not silently drop a consumer forever."""
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        failing = _RecordingConsumer(fail=True)
        registry.register(camera_id, failing)

        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))
        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))

        assert registry.consumers_for(camera_id) == [failing]
        assert registry.failure_count(failing) == 2

    def test_unregistering_a_failed_consumer_clears_its_failure_count(self) -> None:
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        failing = _RecordingConsumer(fail=True)
        registry.register(camera_id, failing)
        registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))
        assert registry.failure_count(failing) == 1

        registry.unregister(camera_id, failing)

        assert registry.failure_count(failing) == 0


class TestConcurrentDispatch:
    def test_concurrent_register_and_dispatch_from_multiple_threads(self) -> None:
        """Mirrors the real cross-thread contract: register/unregister
        called from asyncio-side code, dispatch called from a GStreamer
        streaming thread -- both must be safe to interleave."""
        registry: ConsumerRegistry[_RecordingConsumer] = ConsumerRegistry()
        camera_id = uuid.uuid4()
        stop = threading.Event()
        errors: list[Exception] = []

        def _register_unregister_loop() -> None:
            try:
                while not stop.is_set():
                    consumer = _RecordingConsumer()
                    registry.register(camera_id, consumer)
                    registry.unregister(camera_id, consumer)
            except Exception as exc:  # noqa: BLE001 -- captured for the test assertion
                errors.append(exc)

        def _dispatch_loop() -> None:
            try:
                while not stop.is_set():
                    registry.dispatch(camera_id, lambda c: c(camera_id, "buf"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=_register_unregister_loop),
            threading.Thread(target=_dispatch_loop),
            threading.Thread(target=_dispatch_loop),
        ]
        for t in threads:
            t.start()
        stop.set()
        for t in threads:
            t.join(timeout=5)

        assert errors == []
        assert all(not t.is_alive() for t in threads)
