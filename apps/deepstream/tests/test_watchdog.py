"""Tests for siv/watchdog.py -- RM-11.SIV Watchdog requirement.

Visibility only: check_once() must never mutate pipeline state, only
observe HeartbeatRegistry/PerformanceInstrumentation and log. Fully
SDK-free -- no DeepStream/GStreamer/Postgres dependency.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
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
        instrumentation=PerformanceInstrumentation(pgie_is_placeholder=True),
        settings=settings or WatchdogSettings(),
        bus=bus,
    )


class TestNoActivityIsUnhealthy:
    def test_every_beat_component_starts_unhealthy(self) -> None:
        watchdog = _make_watchdog()

        statuses = watchdog.check_once()

        for component in ("camera", "rtsp", "pgie", "tracker", "sgie", "incident", "alarm"):
            assert statuses[component].healthy is False

    def test_pipeline_fps_unhealthy_before_any_frame(self) -> None:
        watchdog = _make_watchdog()

        statuses = watchdog.check_once()

        assert statuses["pipeline_fps"].healthy is False
        assert statuses["pipeline_fps"].reason == "no frames processed yet"


class TestBeatComponentsBecomeHealthy:
    def test_beaten_component_reports_healthy(self) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        watchdog = _make_watchdog(heartbeat=heartbeat)

        statuses = watchdog.check_once()

        assert statuses["pgie"].healthy is True

    def test_pipeline_fps_healthy_once_frames_are_recorded(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.record_frame(ingress_seconds=1.0, metadata_seconds=1.01)
        watchdog = Watchdog(
            heartbeat_registry=HeartbeatRegistry(),
            instrumentation=instrumentation,
            settings=WatchdogSettings(),
        )

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
            # Force staleness without sleeping: lower the threshold below
            # the (tiny but nonzero) time elapsed since the beat above.
            watchdog._settings.stale_after_seconds.pgie = 0.0  # noqa: SLF001 -- test-only override
            watchdog.check_once()  # falling edge: healthy -> stale, must log
            watchdog.check_once()  # still stale -- must not log again

        warnings = [r for r in caplog.records if "pgie stalled" in r.getMessage()]
        assert len(warnings) == 1
