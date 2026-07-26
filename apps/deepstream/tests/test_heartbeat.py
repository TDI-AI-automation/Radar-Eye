"""Tests for apps.deepstream.app.health.heartbeat."""

from __future__ import annotations

import uuid

from apps.deepstream.app.health.heartbeat import FrameCounter, HeartbeatScheduler

_CAMERA_A = uuid.uuid4()
_CAMERA_B = uuid.uuid4()


class FakeHealthCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, str, float | None]] = []

    def record_camera_heartbeat(self, camera_id, status="CONNECTED", fps=None, timestamp=None):
        self.calls.append((camera_id, status, fps))


class TestFrameCounter:
    def test_increment_and_snapshot(self) -> None:
        counter = FrameCounter()
        counter.increment(_CAMERA_A)
        counter.increment(_CAMERA_A)
        counter.increment(_CAMERA_B)

        snapshot = counter.snapshot_and_reset()

        assert snapshot == {_CAMERA_A: 2, _CAMERA_B: 1}

    def test_snapshot_resets_counts(self) -> None:
        counter = FrameCounter()
        counter.increment(_CAMERA_A)
        counter.snapshot_and_reset()

        assert counter.snapshot_and_reset() == {}

    def test_camera_with_no_frames_is_absent_from_snapshot(self) -> None:
        counter = FrameCounter()
        assert counter.snapshot_and_reset() == {}


class TestHeartbeatScheduler:
    def test_tick_reports_fps_for_connected_cameras(self) -> None:
        counter = FrameCounter()
        for _ in range(30):
            counter.increment(_CAMERA_A)
        collector = FakeHealthCollector()
        scheduler = HeartbeatScheduler(
            health_collector=collector,
            frame_counter=counter,
            camera_ids=[_CAMERA_A],
            status_provider=lambda _camera_id: "CONNECTED",
            interval_seconds=1.0,
        )

        scheduler.tick()

        assert collector.calls == [(_CAMERA_A, "CONNECTED", 30.0)]

    def test_tick_reports_none_fps_for_disconnected_cameras(self) -> None:
        counter = FrameCounter()
        counter.increment(_CAMERA_A)  # stray frames from just before disconnect
        collector = FakeHealthCollector()
        scheduler = HeartbeatScheduler(
            health_collector=collector,
            frame_counter=counter,
            camera_ids=[_CAMERA_A],
            status_provider=lambda _camera_id: "DISCONNECTED",
            interval_seconds=1.0,
        )

        scheduler.tick()

        assert collector.calls == [(_CAMERA_A, "DISCONNECTED", None)]

    def test_tick_covers_every_known_camera_even_with_no_frames(self) -> None:
        counter = FrameCounter()
        collector = FakeHealthCollector()
        scheduler = HeartbeatScheduler(
            health_collector=collector,
            frame_counter=counter,
            camera_ids=[_CAMERA_A, _CAMERA_B],
            status_provider=lambda _camera_id: "CONNECTED",
            interval_seconds=2.0,
        )

        scheduler.tick()

        assert collector.calls == [(_CAMERA_A, "CONNECTED", 0.0), (_CAMERA_B, "CONNECTED", 0.0)]

    def test_tick_resets_counts_between_calls(self) -> None:
        counter = FrameCounter()
        counter.increment(_CAMERA_A)
        collector = FakeHealthCollector()
        scheduler = HeartbeatScheduler(
            health_collector=collector,
            frame_counter=counter,
            camera_ids=[_CAMERA_A],
            status_provider=lambda _camera_id: "CONNECTED",
            interval_seconds=1.0,
        )

        scheduler.tick()
        scheduler.tick()

        assert collector.calls[1] == (_CAMERA_A, "CONNECTED", 0.0)
