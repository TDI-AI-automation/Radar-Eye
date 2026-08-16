"""Hardware-agnostic Alarm Service integration and threat filtering.

Source:
  - docs/ADR_INDEX.md (ADR-012: Alarm Integration Protocol, ADR-026: Alarm Trigger Policy,
    ADR-029: Post-Media-Architecture-Reset Pipeline Decomposition)
  - docs/THREAT_ENGINE_SPEC.md (Alarm Policy: HIGH/FIRE eligible, others excluded)
  - docs/IMPLEMENTATION_ROADMAP.md (RM-10 deliverables and acceptance criteria)

Relocated from ``services/incident_service`` to ``services/alert_service``
under ADR-029 Phase 6: alarm-eligibility ownership (ADR-026's HIGH/FIRE rule)
moved from an undifferentiated "Alarm Service" to Alert Service specifically.
Only the module's location and caller changed -- the class itself, its
filtering rule, and its hardware-adapter boundary are unchanged from RM-10.

Integration boundary: ``trigger()`` is a plain, timing-free public entry
point, called by ``services/alert_service/main.py``'s own dispatch loop in
response to ``AlarmEligibleEvent`` (Incident Service's republication of
Threat Engine's ``EscalationSignalType.ALARM_ELIGIBLE`` -- see
``shared/events/payloads.py``'s ``AlarmEligiblePayload`` docstring for why
that event exists). ``trigger()`` itself contains no escalation-timing
logic -- Threat Engine remains the sole owner of sustained-duration timing
(ADR-021); by the time this is called, that decision has already been made.

Per RM-10 requirements (unchanged by the ADR-029 relocation):
  - Filters alarm requests: ONLY HIGH (and FIRE, always resolved to HIGH by the
    Threat Engine per ADR-015/RM-06) trigger alarms. MEDIUM, LOW, ALLY, OBSERVE,
    and HUMAN_REVIEW are explicitly ignored (ADR-026).
  - Hardware-agnostic AlarmAdapter interface supporting Relay Controllers, GPIO Relays,
    Sirens, and Beacon Lights (ADR-012).
  - MockAlarmAdapter included for hardware-free development and testing environments.
  - Fail-safe process shutdown behavior (`stop()`) automatically silences active outputs.
  - Operator manual silence (`silence()`) and clear (`clear()`) capabilities.
  - Publishes operational `SystemEvent` audit messages onto the internal EventBus, and
    (closing a previously-documented gap -- see docs/IMPLEMENTATION_STATUS.md's Incident
    Service row before this change) the `AlarmRequestedEvent` EVENT_CONTRACTS.md
    documents this service as producing, so Hardware Action Service (ADR-029 Phase 7,
    not yet built) has a real event to consume once it exists.
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
from shared.events.payloads import AlarmRequestedPayload, SystemEventPayload
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

    async def trigger(
        self,
        *,
        camera_id: uuid.UUID,
        track_id: int,
        incident_id: uuid.UUID,
        threat_level: ThreatLevel,
        reason: str,
        timestamp: datetime | None = None,
    ) -> AlarmRecord | None:
        """Public in-process entry point for the future Threat Engine Runtime
        Adapter (RM-11). Contains no escalation-timing logic -- the Threat
        Engine remains the sole source of timing decisions (ADR-021).

        Enforces ADR-026: Alarms are ONLY eligible for HIGH (and FIRE, always
        resolved to HIGH upstream). Ignores MEDIUM, LOW, ALLY, OBSERVE, or
        HUMAN_REVIEW.
        """
        if threat_level is not ThreatLevel.HIGH:
            logger.warning(
                "Rejected alarm request for incident %s: threat_level %s is not eligible (ADR-026)",
                incident_id,
                threat_level.value,
            )
            return None

        # Idempotency check: if an active alarm already exists for this incident, return it
        existing = self._records.get(incident_id)
        if existing is not None and existing.state is AlarmState.ACTIVE:
            return existing

        now = timestamp or datetime.now(timezone.utc)
        record = AlarmRecord(
            alarm_id=uuid.uuid4(),
            incident_id=incident_id,
            camera_id=camera_id,
            track_id=track_id,
            threat_level=threat_level,
            reason=reason,
            state=AlarmState.ACTIVE,
            triggered_at=now,
            target_type=self._default_target,
        )

        self._records[incident_id] = record
        await self._adapter.trigger_alarm(record)

        if self._bus is not None:
            await self._bus.publish(
                AlarmRequestedEvent(
                    event_type="AlarmRequestedEvent",
                    source="alert_service",
                    timestamp=now,
                    payload=AlarmRequestedPayload(
                        incident_id=incident_id,
                        camera_id=camera_id,
                        track_id=track_id,
                        threat_level=threat_level,
                        reason=reason,
                    ),
                )
            )
            await self._bus.publish(
                SystemEvent(
                    event_type="SystemEvent",
                    source="alarm_service",
                    timestamp=now,
                    payload=SystemEventPayload(
                        severity="WARNING",
                        source_component="alarm_service",
                        message=(
                            f"Alarm triggered for incident {incident_id} "
                            f"(camera={camera_id}, threat={threat_level.value}, "
                            f"reason={reason})"
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
