"""Tests for services.alert_service.main -- the Alert Service process's own
internal IncidentCreatedEvent/AlarmEligibleEvent/IncidentUpdatedEvent
dispatch logic (ADR-029 Phase 6). AlertService/AlarmService are mocked out:
this module's own job is only to wire them together correctly, not to
re-test their already-covered business logic (test_service.py, test_alarm.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.alert_service import main as alert_main
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.events.payloads import (
    AlarmEligiblePayload,
    IncidentCreatedPayload,
    IncidentUpdatedPayload,
)
from shared.events.types import AlarmEligibleEvent, IncidentCreatedEvent, IncidentUpdatedEvent

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_incident_created(
    *, camera_id: uuid.UUID, track_id: int, threat_level: ThreatLevel
) -> IncidentCreatedEvent:
    return IncidentCreatedEvent(
        event_type="IncidentCreatedEvent",
        source="incident_service",
        timestamp=T0,
        payload=IncidentCreatedPayload(
            incident_id=uuid.uuid4(),
            camera_id=camera_id,
            track_id=track_id,
            incident_type=IncidentType.THREAT,
            threat_level=threat_level,
            status=IncidentStatus.NEW,
        ),
    )


def _make_alarm_eligible(*, camera_id: uuid.UUID, track_id: int) -> AlarmEligibleEvent:
    return AlarmEligibleEvent(
        event_type="AlarmEligibleEvent",
        source="incident_service",
        timestamp=T0,
        payload=AlarmEligiblePayload(
            incident_id=uuid.uuid4(),
            camera_id=camera_id,
            track_id=track_id,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
        ),
    )


def _make_incident_updated(
    *, incident_id: uuid.UUID, new_status: IncidentStatus
) -> IncidentUpdatedEvent:
    return IncidentUpdatedEvent(
        event_type="IncidentUpdatedEvent",
        source="incident_service",
        timestamp=T0,
        payload=IncidentUpdatedPayload(
            incident_id=incident_id,
            old_status=IncidentStatus.ACTIVE,
            new_status=new_status,
        ),
    )


@pytest.fixture
def alert_service() -> MagicMock:
    service = MagicMock()
    service.raise_alert = AsyncMock()
    service.resolve = AsyncMock()
    return service


@pytest.fixture
def alarm_service() -> MagicMock:
    service = MagicMock()
    service.trigger = AsyncMock()
    service.clear = AsyncMock()
    return service


@pytest.mark.asyncio
class TestIncidentCreatedHandling:
    async def test_any_severity_raises_an_alert(self, alert_service: MagicMock) -> None:
        camera_id = uuid.uuid4()
        event = _make_incident_created(
            camera_id=camera_id, track_id=7, threat_level=ThreatLevel.MEDIUM
        )

        await alert_main._handle_incident_created(event, alert_service=alert_service)

        alert_service.raise_alert.assert_awaited_once_with(
            incident_id=event.payload.incident_id,
            camera_id=camera_id,
            severity=ThreatLevel.MEDIUM,
            timestamp=T0,
        )

    async def test_never_triggers_an_alarm_directly(self, alert_service: MagicMock) -> None:
        """Alarm-eligibility is driven exclusively by AlarmEligibleEvent, not
        by IncidentCreatedEvent's threat_level -- see AlarmEligiblePayload's
        docstring for why the two are separate, sequential thresholds."""
        event = _make_incident_created(
            camera_id=uuid.uuid4(), track_id=7, threat_level=ThreatLevel.HIGH
        )

        await alert_main._handle_incident_created(event, alert_service=alert_service)

        alert_service.raise_alert.assert_awaited_once()


@pytest.mark.asyncio
class TestAlarmEligibleHandling:
    async def test_triggers_the_alarm_with_the_event_s_own_incident_id(
        self, alarm_service: MagicMock
    ) -> None:
        camera_id = uuid.uuid4()
        event = _make_alarm_eligible(camera_id=camera_id, track_id=7)

        await alert_main._handle_alarm_eligible(event, alarm_service=alarm_service)

        alarm_service.trigger.assert_awaited_once_with(
            camera_id=camera_id,
            track_id=7,
            incident_id=event.payload.incident_id,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0,
        )


@pytest.mark.asyncio
class TestIncidentUpdatedHandling:
    @pytest.mark.parametrize("status", [IncidentStatus.RESOLVED, IncidentStatus.ARCHIVED])
    async def test_terminal_status_resolves_alert_and_clears_alarm(
        self, alert_service: MagicMock, alarm_service: MagicMock, status: IncidentStatus
    ) -> None:
        incident_id = uuid.uuid4()
        event = _make_incident_updated(incident_id=incident_id, new_status=status)

        await alert_main._handle_incident_updated(
            event, alert_service=alert_service, alarm_service=alarm_service
        )

        alert_service.resolve.assert_awaited_once_with(incident_id)
        alarm_service.clear.assert_awaited_once_with(incident_id)

    @pytest.mark.parametrize("status", [IncidentStatus.ACTIVE, IncidentStatus.ACKNOWLEDGED])
    async def test_non_terminal_status_does_nothing(
        self, alert_service: MagicMock, alarm_service: MagicMock, status: IncidentStatus
    ) -> None:
        event = _make_incident_updated(incident_id=uuid.uuid4(), new_status=status)

        await alert_main._handle_incident_updated(
            event, alert_service=alert_service, alarm_service=alarm_service
        )

        alert_service.resolve.assert_not_called()
        alarm_service.clear.assert_not_called()
