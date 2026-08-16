"""Alert generation, severity, deduplication, and operator notification.

Source: docs/ADR_INDEX.md (ADR-029, Phase 6). Authority: ADR-029.

Owns exactly one business capability, per ADR-029's governing principle 2:
turning an incident into an operator-facing alert. Every incident Alert
Service is notified of (any severity -- Incident Service only ever creates
one for a track that already crossed Threat Engine's ``INCIDENT_ELIGIBLE``
threshold, ADR-021) raises an alert; this is deliberately broader than
alarm-eligibility (``services/alert_service/alarm.py``'s HIGH/FIRE-only
rule, ADR-026) -- an operator is notified of every incident, only HIGH/FIRE
additionally activates physical hardware.

In-memory record store, one entry per incident -- the same pattern already
established by ``AlarmService`` (``alarm.py``, moved here from
``services/incident_service`` under this same ADR-029 phase) rather than a
new persisted ``alerts`` table: no such table is defined anywhere in
docs/DATABASE_SCHEMA.md, and ADR-029 does not mandate one -- inventing a
persistence schema here would be an unapproved architecture addition
(CLAUDE.md: "Never modify architecture without explicit approval").
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from services.alert_service.notification import NotificationChannel
from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import EventBus
from shared.events.payloads import AlertRaisedPayload
from shared.events.types import AlertRaisedEvent

logger = logging.getLogger(__name__)

UI_CHANNEL = "ui"
"""Always present -- see notification.py's module docstring for why no
NotificationChannel implementation is needed for it."""


class AlertState(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


@dataclass
class AlertRecord:
    """In-memory record tracking an active or past alert."""

    alert_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    severity: ThreatLevel
    channels: list[str]
    state: AlertState
    raised_at: datetime
    resolved_at: datetime | None = None


class AlertService:
    """Owns alert creation, per-incident deduplication, and dispatch to
    notification channels (ADR-029 Phase 6)."""

    def __init__(
        self,
        bus: EventBus | None = None,
        notification_channels: list[NotificationChannel] | None = None,
    ) -> None:
        self._bus = bus
        self._notification_channels = notification_channels or []
        self._records: dict[uuid.UUID, AlertRecord] = {}

    async def raise_alert(
        self,
        *,
        incident_id: uuid.UUID,
        camera_id: uuid.UUID,
        severity: ThreatLevel,
        timestamp: datetime | None = None,
    ) -> AlertRecord:
        """Create (or return the existing) active alert for this incident.

        Idempotent, mirroring ``IncidentService.handle_escalation()`` and
        ``AlarmService.trigger()``'s own precedent: a repeat call for an
        incident that already has an active alert returns the existing
        record and still publishes ``AlertRaisedEvent`` with
        ``deduplicated=True`` (the documented contract field, EVENT_CONTRACTS.md)
        rather than silently doing nothing -- the frontend can distinguish a
        genuinely new alert from a repeat notification without needing to
        track alert IDs itself.
        """
        existing = self._records.get(incident_id)
        if existing is not None and existing.state is AlertState.ACTIVE:
            await self._publish(existing, deduplicated=True)
            return existing

        now = timestamp or datetime.now(timezone.utc)
        record = AlertRecord(
            alert_id=uuid.uuid4(),
            incident_id=incident_id,
            camera_id=camera_id,
            severity=severity,
            channels=[UI_CHANNEL],
            state=AlertState.ACTIVE,
            raised_at=now,
        )

        for channel in self._notification_channels:
            try:
                sent = await channel.send(record)
            except Exception:
                logger.exception(
                    "Notification channel %s failed to send for incident %s",
                    channel.name,
                    incident_id,
                )
                continue
            if sent:
                record.channels.append(channel.name)

        self._records[incident_id] = record
        await self._publish(record, deduplicated=False)
        return record

    async def resolve(self, incident_id: uuid.UUID) -> AlertRecord | None:
        """Mark an incident's alert resolved (e.g. the incident itself was
        resolved/archived). Idempotent: resolving an already-resolved or
        never-raised incident's alert returns None."""
        record = self._records.get(incident_id)
        if record is None or record.state is AlertState.RESOLVED:
            return None
        record.state = AlertState.RESOLVED
        record.resolved_at = datetime.now(timezone.utc)
        return record

    def get_active_alerts(self) -> list[AlertRecord]:
        return [r for r in self._records.values() if r.state is AlertState.ACTIVE]

    def get_all_alerts(self) -> list[AlertRecord]:
        return list(self._records.values())

    async def _publish(self, record: AlertRecord, *, deduplicated: bool) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            AlertRaisedEvent(
                event_type="AlertRaisedEvent",
                source="alert_service",
                payload=AlertRaisedPayload(
                    alert_id=record.alert_id,
                    incident_id=record.incident_id,
                    camera_id=record.camera_id,
                    severity=record.severity,
                    channels=list(record.channels),
                    deduplicated=deduplicated,
                ),
            )
        )
