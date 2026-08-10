"""Tests for siv/watchdog.py -- RM-11.SIV Watchdog requirement.

Visibility only: check_once() must never mutate pipeline state, only
observe HeartbeatRegistry and log. Fully SDK-free -- no DeepStream/
GStreamer/Postgres dependency.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.siv.watchdog import Watchdog
from shared.events.bus import InProcessEventBus
from shared.events.envelope import EventEnvelope
from shared.events.payloads import SystemEventPayload
from shared.events.types import SystemEvent


def _make_watchdog(
    *,
    heartbeat: HeartbeatRegistry | None = None,
    bus=None,
    settings: WatchdogSettings | None = None,
) -> Watchdog:
    return Watchdog(
        heartbeat_registry=heartbeat or HeartbeatRegistry(),
        settings=settings or WatchdogSettings(),
        bus=bus,
    )


class TestNoActivityIsUnhealthy:
    def test_every_beat_component_starts_unhealthy(self) -> None:
        watchdog = _make_watchdog()

        statuses = watchdog.check_once()

        for component in (
            "camera",
            "rtsp",
            "pgie",
            "tracker",
            "sgie",
            "pipeline_fps",
        ):
            assert statuses[component].healthy is False

    def test_pipeline_fps_unhealthy_before_any_beat(self) -> None:
        watchdog = _make_watchdog()

        statuses = watchdog.check_once()

        assert statuses["pipeline_fps"].healthy is False
        assert statuses["pipeline_fps"].reason == "no activity recorded yet"


class TestBeatComponentsBecomeHealthy:
    def test_beaten_component_reports_healthy(self) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        watchdog = _make_watchdog(heartbeat=heartbeat)

        statuses = watchdog.check_once()

        assert statuses["pgie"].healthy is True

    def test_pipeline_fps_healthy_once_beaten(self) -> None:
        """pipeline_fps is beaten by RuntimeAdapter.on_frame_observation --
        see runtime_adapter.py -- reading through the same shared
        HeartbeatRegistry as every other component (Unified Heartbeat's
        one source of truth; a real hardware run caught a prior version of
        this class deriving it separately, which the dashboard couldn't see)."""
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pipeline_fps")
        watchdog = _make_watchdog(heartbeat=heartbeat)

        statuses = watchdog.check_once()

        assert statuses["pipeline_fps"].healthy is True
        assert statuses["pipeline_fps"].counter == 1


class TestNeverMutatesState:
    def test_check_once_does_not_change_heartbeat_counters(self) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        watchdog = _make_watchdog(heartbeat=heartbeat)

        watchdog.check_once()
        watchdog.check_once()

        # Watchdog only reads -- counter must still reflect the single
        # real beat(), not anything the watchdog itself did.
        assert heartbeat.status("pgie", stale_after_seconds=5.0).counter == 1


@pytest.mark.asyncio
class TestEventBusLiveness:
    async def test_event_bus_becomes_healthy_after_an_event_is_published(self) -> None:
        bus = InProcessEventBus()
        try:
            heartbeat = HeartbeatRegistry()
            watchdog = _make_watchdog(heartbeat=heartbeat, bus=bus)

            event: EventEnvelope = SystemEvent(
                event_type="SystemEvent",
                source="test",
                payload=SystemEventPayload(
                    severity="INFO", source_component="test", message="hello"
                ),
            )
            await bus.publish(event)
            await asyncio.sleep(0.05)  # InProcessEventBus delivery is async, see bus.py

            statuses = watchdog.check_once()
            assert statuses["event_bus"].healthy is True
        finally:
            await bus.stop()

    async def test_event_bus_unhealthy_with_no_bus_configured(self) -> None:
        watchdog = _make_watchdog(bus=None)

        statuses = watchdog.check_once()

        assert statuses["event_bus"].healthy is False


class TestAuditLogOnFallingEdge:
    def test_logs_warning_only_once_when_component_goes_stale(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        watchdog = _make_watchdog(heartbeat=heartbeat)

        with caplog.at_level(logging.WARNING, logger="radar_eye.audit"):
            watchdog.check_once()  # healthy -- just beaten, default threshold
            # Force staleness deterministically via an injected clock
            # reading rather than lowering the threshold and racing real
            # elapsed time: on a fast/coarse-clock runner, the elapsed time
            # since the beat above can measure as exactly 0.0s, which never
            # exceeds a 0.0s threshold (age <= stale_after_seconds) and the
            # falling edge silently never fires.
            last_seen = heartbeat.status("pgie", stale_after_seconds=5.0).last_seen_monotonic
            stale_now = last_seen + 10.0  # default pgie threshold is 5.0s
            watchdog.check_once(now=stale_now)  # falling edge: healthy -> stale, must log
            watchdog.check_once(now=stale_now)  # still stale -- must not log again

        warnings = [r for r in caplog.records if "pgie stalled" in r.getMessage()]
        assert len(warnings) == 1
