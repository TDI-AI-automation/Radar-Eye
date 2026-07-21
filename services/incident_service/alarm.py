"""Hardware-agnostic Alarm Service integration and threat filtering.

Source:
  - docs/ADR_INDEX.md (ADR-012: Alarm Integration Protocol, ADR-026: Alarm Trigger Policy)
  - docs/THREAT_ENGINE_SPEC.md (Alarm Policy: HIGH/FIRE eligible, others excluded)
  - docs/EVENT_CONTRACTS.md (AlarmRequestedEvent payload contract)
  - docs/FRONTEND_BACKEND_CONTRACTS.md (/ws/alarms WebSocket payload)
  - docs/IMPLEMENTATION_ROADMAP.md (RM-10 deliverables and acceptance criteria)

Per RM-10 requirements:
  - Filters AlarmRequestedEvent: ONLY HIGH (and FIRE elevated to HIGH) trigger alarms.
    MEDIUM, LOW, ALLY, OBSERVE, and HUMAN_REVIEW events are explicitly ignored (ADR-026).
  - Hardware-agnostic AlarmAdapter interface supporting Relay Controllers, GPIO Relays,
    Sirens, and Beacon Lights (ADR-012).
  - MockAlarmAdapter included for hardware-free development and testing environments.
  - Fail-safe process shutdown behavior (`stop()`) automatically silences active outputs.
  - Operator manual silence (`silence()`) and clear (`clear()`) capabilities.
  - Publishes operational `SystemEvent` audit messages onto the internal EventBus.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import EventBus
from shared.events.payloads import SystemEventPayload
from shared.events.types import AlarmRequestedEvent, SystemEvent

logger = logging.getLogger(__name__)


class AlarmTargetType(str, Enum):
    """Supported hardware targets per ADR-012."""

    RELAY = "relay"
    GPIO = "gpio"
    SIREN = "siren"
    BEACON = "beacon"


class AlarmState(str, Enum):
    """Alarm lifecycle state."""

    ACTIVE = "ACTIVE"
    SILENCED = "SILENCED"
    CLEARED = "CLEARED"


@dataclass
class AlarmRecord:
    """In-memory record tracking an active or past alarm activation."""

    alarm_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    threat_level: ThreatLevel
    reason: str
    state: AlarmState
    triggered_at: datetime
    silenced_at: datetime | None = None
    cleared_at: datetime | None = None
    target_type: AlarmTargetType = AlarmTargetType.SIREN


class AlarmAdapter(ABC):
    """Abstract hardware driver interface for alarm actuators (ADR-012)."""

    @abstractmethod
    async def trigger_alarm(self, record: AlarmRecord) -> bool:
        """Trigger physical alarm output (e.g. energize relay, sound siren)."""

    @abstractmethod
    async def silence_alarm(self, record: AlarmRecord) -> bool:
        """Silence physical alarm output without clearing the incident."""

    @abstractmethod
    async def clear_alarm(self, record: AlarmRecord) -> bool:
        """De-energize output and reset hardware state."""


class MockAlarmAdapter(AlarmAdapter):
    """In-memory alarm adapter for testing and dev environments."""

    def __init__(self) -> None:
        self.triggered_records: list[AlarmRecord] = []
        self.silenced_records: list[AlarmRecord] = []
        self.cleared_records: list[AlarmRecord] = []

    async def trigger_alarm(self, record: AlarmRecord) -> bool:
        self.triggered_records.append(record)
        return True

    async def silence_alarm(self, record: AlarmRecord) -> bool:
        self.silenced_records.append(record)
        return True

    async def clear_alarm(self, record: AlarmRecord) -> bool:
        self.cleared_records.append(record)
        return True


class AlarmService:
    """Owns alarm activation, threat level eligibility filtering, manual silence,
    and fail-safe hardware control (ADR-012, ADR-026).
    """

    def __init__(
        self,
        bus: EventBus | None = None,
        adapter: AlarmAdapter | None = None,
        default_target: AlarmTargetType = AlarmTargetType.SIREN,
    ) -> None:
        self._bus = bus
        self._adapter = adapter or MockAlarmAdapter()
        self._default_target = default_target
        self._records: dict[uuid.UUID, AlarmRecord] = {}

    @property
    def adapter(self) -> AlarmAdapter:
        """Return the underlying alarm hardware adapter."""
        return self._adapter

    async def on_alarm_requested(self, event: AlarmRequestedEvent) -> AlarmRecord | None:
        """Consume AlarmRequestedEvent from threat engine / bus.

        Enforces ADR-026: Alarms are ONLY eligible for HIGH (and FIRE elevated to HIGH).
        Ignores any requests for MEDIUM, LOW, ALLY, OBSERVE, or HUMAN_REVIEW.
        """
        payload = event.payload
        if payload.threat_level is not ThreatLevel.HIGH:
            logger.warning(
                "Rejected alarm request for incident %s: threat_level %s is not eligible (ADR-026)",
                payload.incident_id,
                payload.threat_level.value,
            )
            return None

        # Idempotency check: if an active alarm already exists for this incident, return it
        existing = self._records.get(payload.incident_id)
        if existing is not None and existing.state is AlarmState.ACTIVE:
            return existing

        now = datetime.now(timezone.utc)
        record = AlarmRecord(
            alarm_id=uuid.uuid4(),
            incident_id=payload.incident_id,
            camera_id=payload.camera_id,
            track_id=payload.track_id,
            threat_level=payload.threat_level,
            reason=payload.reason,
            state=AlarmState.ACTIVE,
            triggered_at=now,
            target_type=self._default_target,
        )

        self._records[payload.incident_id] = record
        await self._adapter.trigger_alarm(record)

        if self._bus is not None:
            await self._bus.publish(
                SystemEvent(
                    event_type="SystemEvent",
                    source="alarm_service",
                    timestamp=now,
                    payload=SystemEventPayload(
                        severity="WARNING",
                        source_component="alarm_service",
                        message=(
                            f"Alarm triggered for incident {payload.incident_id} "
                            f"(camera={payload.camera_id}, threat={payload.threat_level.value}, "
                            f"reason={payload.reason})"
                        ),
                    ),
                )
            )

        return record

    async def silence(self, incident_id: uuid.UUID | None = None) -> list[AlarmRecord]:
        """Silence active alarm for an incident, or all active alarms if incident_id is None.

        Transitions state to SILENCED and invokes adapter.silence_alarm().
        """
        now = datetime.now(timezone.utc)
        silenced: list[AlarmRecord] = []

        targets = (
            [self._records[incident_id]]
            if incident_id is not None and incident_id in self._records
            else list(self._records.values())
        )

        for record in targets:
            if record.state is AlarmState.ACTIVE:
                record.state = AlarmState.SILENCED
                record.silenced_at = now
                await self._adapter.silence_alarm(record)
                silenced.append(record)

        if silenced and self._bus is not None:
            msg = (
                f"Alarm silenced for incident {incident_id}"
                if incident_id is not None
                else f"All active alarms silenced ({len(silenced)} alarms)"
            )
            await self._bus.publish(
                SystemEvent(
                    event_type="SystemEvent",
                    source="alarm_service",
                    timestamp=now,
                    payload=SystemEventPayload(
                        severity="INFO",
                        source_component="alarm_service",
                        message=msg,
                    ),
                )
            )

        return silenced

    async def clear(self, incident_id: uuid.UUID) -> AlarmRecord | None:
        """Clear an active or silenced alarm for an incident when resolved."""
        record = self._records.get(incident_id)
        if record is None or record.state is AlarmState.CLEARED:
            return None

        now = datetime.now(timezone.utc)
        record.state = AlarmState.CLEARED
        record.cleared_at = now
        await self._adapter.clear_alarm(record)

        if self._bus is not None:
            await self._bus.publish(
                SystemEvent(
                    event_type="SystemEvent",
                    source="alarm_service",
                    timestamp=now,
                    payload=SystemEventPayload(
                        severity="INFO",
                        source_component="alarm_service",
                        message=f"Alarm cleared for incident {incident_id}",
                    ),
                )
            )

        return record

    async def stop(self) -> list[AlarmRecord]:
        """Fail-safe shutdown procedure.

        Silences all active physical alarm outputs upon process termination.
        """
        logger.info("Executing AlarmService fail-safe shutdown...")
        return await self.silence(incident_id=None)

    def get_active_alarms(self) -> list[AlarmRecord]:
        """Return list of currently active (non-silenced, non-cleared) alarms."""
        return [r for r in self._records.values() if r.state is AlarmState.ACTIVE]

    def get_all_alarms(self) -> list[AlarmRecord]:
        """Return all tracked alarm records."""
        return list(self._records.values())
