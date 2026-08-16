"""Unit tests for AlertService (ADR-029 Phase 6).

Source: docs/ADR_INDEX.md (ADR-029). docs/EVENT_CONTRACTS.md (AlertRaisedEvent).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from services.alert_service.notification import NotificationChannel
from services.alert_service.service import AlertService, AlertState
from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import InProcessEventBus

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _raise_kwargs(
    *,
    incident_id: uuid.UUID | None = None,
    camera_id: uuid.UUID | None = None,
    severity: ThreatLevel = ThreatLevel.HIGH,
) -> dict:
    return {
        "incident_id": incident_id or uuid.uuid4(),
        "camera_id": camera_id or uuid.uuid4(),
        "severity": severity,
        "timestamp": T0,
    }


def _collecting_handler(sink: list):
    async def handler(event):
        sink.append(event)

    return handler


@pytest.mark.asyncio
class TestAlertGeneration:
    """Every incident raises an alert, regardless of severity -- unlike
    AlarmService, which is HIGH/FIRE-only (ADR-026)."""

    @pytest.mark.parametrize(
        "severity",
        [
            ThreatLevel.HIGH,
            ThreatLevel.MEDIUM,
            ThreatLevel.LOW,
            ThreatLevel.ALLY,
            ThreatLevel.OBSERVE,
            ThreatLevel.HUMAN_REVIEW,
        ],
    )
    async def test_any_severity_raises_an_alert(self, severity: ThreatLevel) -> None:
        service = AlertService()
        kwargs = _raise_kwargs(severity=severity)

        record = await service.raise_alert(**kwargs)

        assert record.state is AlertState.ACTIVE
        assert record.severity is severity
        assert record.channels == ["ui"]
        assert len(service.get_active_alerts()) == 1


@pytest.mark.asyncio
class TestAlertDeduplication:
    async def test_repeated_raise_returns_existing_record_and_is_marked_deduplicated(
        self,
    ) -> None:
        bus = InProcessEventBus()
        try:
            events: list = []
            bus.subscribe("AlertRaisedEvent", _collecting_handler(events))
            service = AlertService(bus=bus)
            incident_id = uuid.uuid4()

            rec1 = await service.raise_alert(**_raise_kwargs(incident_id=incident_id))
            rec2 = await service.raise_alert(**_raise_kwargs(incident_id=incident_id))
            await asyncio.sleep(0.05)

            assert rec1.alert_id == rec2.alert_id
            assert len(service.get_active_alerts()) == 1
            assert len(events) == 2
            assert events[0].payload.deduplicated is False
            assert events[1].payload.deduplicated is True
            assert events[1].payload.alert_id == rec1.alert_id
        finally:
            await bus.stop()


@pytest.mark.asyncio
class TestAlertResolution:
    async def test_resolve_marks_alert_resolved(self) -> None:
        service = AlertService()
        kwargs = _raise_kwargs()
        record = await service.raise_alert(**kwargs)

        resolved = await service.resolve(kwargs["incident_id"])

        assert resolved is not None
        assert resolved.alert_id == record.alert_id
        assert resolved.state is AlertState.RESOLVED
        assert resolved.resolved_at is not None
        assert len(service.get_active_alerts()) == 0

    async def test_resolve_is_idempotent(self) -> None:
        service = AlertService()
        kwargs = _raise_kwargs()
        await service.raise_alert(**kwargs)

        await service.resolve(kwargs["incident_id"])
        second = await service.resolve(kwargs["incident_id"])

        assert second is None

    async def test_resolve_unknown_incident_returns_none(self) -> None:
        service = AlertService()
        assert await service.resolve(uuid.uuid4()) is None

    async def test_get_all_alerts_includes_resolved(self) -> None:
        service = AlertService()
        kwargs1 = _raise_kwargs()
        kwargs2 = _raise_kwargs()
        await service.raise_alert(**kwargs1)
        await service.raise_alert(**kwargs2)
        await service.resolve(kwargs1["incident_id"])

        assert len(service.get_all_alerts()) == 2
        assert len(service.get_active_alerts()) == 1


@pytest.mark.asyncio
class TestEventBusIntegration:
    async def test_raise_alert_publishes_alert_raised_event(self) -> None:
        bus = InProcessEventBus()
        try:
            events: list = []
            bus.subscribe("AlertRaisedEvent", _collecting_handler(events))
            service = AlertService(bus=bus)
            kwargs = _raise_kwargs(severity=ThreatLevel.HIGH)

            record = await service.raise_alert(**kwargs)
            await asyncio.sleep(0.05)

            assert len(events) == 1
            assert events[0].payload.alert_id == record.alert_id
            assert events[0].payload.incident_id == kwargs["incident_id"]
            assert events[0].payload.camera_id == kwargs["camera_id"]
            assert events[0].payload.severity is ThreatLevel.HIGH
            assert events[0].payload.channels == ["ui"]
            assert events[0].payload.deduplicated is False
        finally:
            await bus.stop()


@pytest.mark.asyncio
class TestNotificationChannels:
    async def test_successful_channel_send_is_recorded_in_channels(self) -> None:
        class DummyChannel(NotificationChannel):
            name = "sms"

            async def send(self, record) -> bool:
                return True

        service = AlertService(notification_channels=[DummyChannel()])
        record = await service.raise_alert(**_raise_kwargs())

        assert record.channels == ["ui", "sms"]

    async def test_failed_channel_send_is_not_recorded(self) -> None:
        class DummyChannel(NotificationChannel):
            name = "sms"

            async def send(self, record) -> bool:
                return False

        service = AlertService(notification_channels=[DummyChannel()])
        record = await service.raise_alert(**_raise_kwargs())

        assert record.channels == ["ui"]

    async def test_channel_exception_does_not_break_alert_raising(self) -> None:
        class BrokenChannel(NotificationChannel):
            name = "email"

            async def send(self, record) -> bool:
                raise RuntimeError("provider unreachable")

        service = AlertService(notification_channels=[BrokenChannel()])
        record = await service.raise_alert(**_raise_kwargs())

        assert record is not None
        assert record.channels == ["ui"]
