"""Unit tests for AlarmService (RM-10, relocated to services.alert_service
under ADR-029 Phase 6).

Source:
  - docs/ADR_INDEX.md (ADR-012: Hardware-agnostic Alarm Protocol, ADR-026: Alarm Trigger Policy,
    ADR-029: Post-Media-Architecture-Reset Pipeline Decomposition)
  - docs/IMPLEMENTATION_ROADMAP.md (RM-10 acceptance criteria)
  - docs/THREAT_ENGINE_SPEC.md (Alarm eligibility: HIGH only, all others excluded)

trigger() is exercised directly here, simulating Alert Service's own
dispatch loop (services/alert_service/main.py's _handle_alarm_eligible),
which calls it in response to AlarmEligibleEvent -- the same "plain,
timing-free entry point" shape the RM-10 architectural review (Repository
Integration Audit) originally established for the (now superseded)
Threat Engine Runtime Adapter.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from services.alert_service.alarm import (
    AlarmAdapter,
    AlarmRecord,
    AlarmService,
    AlarmState,
    AlarmTargetType,
    MockAlarmAdapter,
)
from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import InProcessEventBus

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _alarm_kwargs(
    *,
    incident_id: uuid.UUID | None = None,
    camera_id: uuid.UUID | None = None,
    track_id: int = 1,
    threat_level: ThreatLevel = ThreatLevel.HIGH,
    reason: str = "sustained_high_threat",
) -> dict:
    return {
        "incident_id": incident_id or uuid.uuid4(),
        "camera_id": camera_id or uuid.uuid4(),
        "track_id": track_id,
        "threat_level": threat_level,
        "reason": reason,
        "timestamp": T0,
    }


def _collecting_handler(sink: list):
    async def handler(event):
        sink.append(event)

    return handler


@pytest.mark.asyncio
class TestAlarmThreatFiltering:
    """Roadmap acceptance criterion & ADR-026: Alarm never fires outside HIGH/FIRE."""

    async def test_high_threat_triggers_alarm(self) -> None:
        service = AlarmService()
        kwargs = _alarm_kwargs(threat_level=ThreatLevel.HIGH)

        record = await service.trigger(**kwargs)

        assert record is not None
        assert record.state is AlarmState.ACTIVE
        assert record.threat_level is ThreatLevel.HIGH
        assert record.incident_id == kwargs["incident_id"]
        assert len(service.get_active_alarms()) == 1

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.triggered_records) == 1
        assert mock_adapter.triggered_records[0].alarm_id == record.alarm_id

    @pytest.mark.parametrize(
        "threat_level",
        [
            ThreatLevel.MEDIUM,
            ThreatLevel.LOW,
            ThreatLevel.ALLY,
            ThreatLevel.OBSERVE,
            ThreatLevel.HUMAN_REVIEW,
        ],
    )
    async def test_non_high_threat_levels_are_rejected(self, threat_level: ThreatLevel) -> None:
        service = AlarmService()
        kwargs = _alarm_kwargs(threat_level=threat_level)

        record = await service.trigger(**kwargs)

        assert record is None
        assert len(service.get_active_alarms()) == 0

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.triggered_records) == 0


@pytest.mark.asyncio
class TestAlarmIdempotency:
    async def test_repeated_alarm_request_returns_existing_active_record(self) -> None:
        service = AlarmService()
        incident_id = uuid.uuid4()
        kwargs1 = _alarm_kwargs(incident_id=incident_id)
        kwargs2 = _alarm_kwargs(incident_id=incident_id)

        rec1 = await service.trigger(**kwargs1)
        rec2 = await service.trigger(**kwargs2)

        assert rec1 is not None and rec2 is not None
        assert rec1.alarm_id == rec2.alarm_id
        assert len(service.get_active_alarms()) == 1

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.triggered_records) == 1


@pytest.mark.asyncio
class TestManualSilenceAndClear:
    async def test_silence_specific_incident_alarm(self) -> None:
        service = AlarmService()
        kwargs = _alarm_kwargs()
        rec = await service.trigger(**kwargs)
        assert rec is not None

        silenced = await service.silence(kwargs["incident_id"])

        assert len(silenced) == 1
        assert silenced[0].state is AlarmState.SILENCED
        assert silenced[0].silenced_at is not None
        assert len(service.get_active_alarms()) == 0

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.silenced_records) == 1

    async def test_silence_all_active_alarms(self) -> None:
        service = AlarmService()
        await service.trigger(**_alarm_kwargs())
        await service.trigger(**_alarm_kwargs())

        silenced = await service.silence()

        assert len(silenced) == 2
        assert all(r.state is AlarmState.SILENCED for r in silenced)
        assert len(service.get_active_alarms()) == 0

    async def test_clear_alarm(self) -> None:
        service = AlarmService()
        kwargs = _alarm_kwargs()
        rec = await service.trigger(**kwargs)
        assert rec is not None

        cleared = await service.clear(kwargs["incident_id"])

        assert cleared is not None
        assert cleared.state is AlarmState.CLEARED
        assert cleared.cleared_at is not None
        assert len(service.get_active_alarms()) == 0

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.cleared_records) == 1

        # Clearing again returns None
        assert await service.clear(kwargs["incident_id"]) is None
        # Clearing non-existent incident returns None
        assert await service.clear(uuid.uuid4()) is None

    async def test_get_all_alarms(self) -> None:
        service = AlarmService()
        kwargs1 = _alarm_kwargs()
        kwargs2 = _alarm_kwargs()
        await service.trigger(**kwargs1)
        await service.trigger(**kwargs2)
        await service.silence(kwargs1["incident_id"])

        all_records = service.get_all_alarms()
        assert len(all_records) == 2


@pytest.mark.asyncio
class TestFailSafeShutdown:
    """Acceptance criterion: fail-safe behavior on service shutdown."""

    async def test_stop_silences_all_active_alarms(self) -> None:
        service = AlarmService()
        await service.trigger(**_alarm_kwargs())
        await service.trigger(**_alarm_kwargs())

        silenced = await service.stop()

        assert len(silenced) == 2
        assert len(service.get_active_alarms()) == 0

        mock_adapter: MockAlarmAdapter = service.adapter  # type: ignore[assignment]
        assert len(mock_adapter.silenced_records) == 2


@pytest.mark.asyncio
class TestCustomAlarmAdapter:
    async def test_custom_adapter_receives_invocations(self) -> None:
        class DummyAdapter(AlarmAdapter):
            def __init__(self) -> None:
                self.triggered = False
                self.silenced = False
                self.cleared = False

            async def trigger_alarm(self, record: AlarmRecord) -> bool:
                self.triggered = True
                return True

            async def silence_alarm(self, record: AlarmRecord) -> bool:
                self.silenced = True
                return True

            async def clear_alarm(self, record: AlarmRecord) -> bool:
                self.cleared = True
                return True

        custom = DummyAdapter()
        service = AlarmService(adapter=custom, default_target=AlarmTargetType.RELAY)

        kwargs = _alarm_kwargs()
        rec = await service.trigger(**kwargs)
        assert rec is not None
        assert rec.target_type is AlarmTargetType.RELAY
        assert custom.triggered is True

        await service.silence(kwargs["incident_id"])
        assert custom.silenced is True

        await service.clear(kwargs["incident_id"])
        assert custom.cleared is True


@pytest.mark.asyncio
class TestSystemEventBusIntegration:
    async def test_publishes_system_events_on_alarm_lifecycle(self) -> None:
        bus = InProcessEventBus()
        try:
            events: list = []
            bus.subscribe("SystemEvent", _collecting_handler(events))

            service = AlarmService(bus=bus)
            kwargs = _alarm_kwargs()

            await service.trigger(**kwargs)
            await service.silence(kwargs["incident_id"])
            await service.clear(kwargs["incident_id"])

            await asyncio.sleep(0.05)  # drain bus subscribers

            assert len(events) == 3
            assert events[0].payload.severity == "WARNING"
            assert "Alarm triggered" in events[0].payload.message
            assert events[1].payload.severity == "INFO"
            assert "Alarm silenced" in events[1].payload.message
            assert events[2].payload.severity == "INFO"
            assert "Alarm cleared" in events[2].payload.message
        finally:
            await bus.stop()

    async def test_trigger_publishes_alarm_requested_event(self) -> None:
        """Closes a previously-documented gap (docs/IMPLEMENTATION_STATUS.md's
        Incident Service row before ADR-029 Phase 6): trigger() must publish
        the AlarmRequestedEvent EVENT_CONTRACTS.md documents this service as
        producing, not only the SystemEvent audit message."""
        bus = InProcessEventBus()
        try:
            events: list = []
            bus.subscribe("AlarmRequestedEvent", _collecting_handler(events))

            service = AlarmService(bus=bus)
            kwargs = _alarm_kwargs()

            record = await service.trigger(**kwargs)
            await asyncio.sleep(0.05)

            assert record is not None
            assert len(events) == 1
            assert events[0].payload.incident_id == kwargs["incident_id"]
            assert events[0].payload.camera_id == kwargs["camera_id"]
            assert events[0].payload.threat_level is ThreatLevel.HIGH
            assert events[0].payload.reason == kwargs["reason"]
        finally:
            await bus.stop()
