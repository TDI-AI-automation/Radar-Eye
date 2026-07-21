"""Incident lifecycle: dedup enforcement, creation, and track-lost auto-close.

Source: docs/INCIDENT_LIFECYCLE.md, docs/DATABASE_SCHEMA.md ("Incident
Deduplication Constraint"). Authority: ADR-024, ADR-025.

Per the RM-07 design review: this service owns incident creation, state
transitions, persistence, publication, idempotency, and lifecycle management.
It explicitly does **not** own threat classification, debounce, hysteresis,
or escalation-timing (those remain exclusively Threat Engine's concern, per
ADR-021). ``handle_escalation()`` is a plain in-process entry point --
called directly by whatever eventually owns the "observe EscalationSignal"
role (the Threat Engine Runtime Adapter, explicitly deferred until a real
per-frame pipeline exists to feed it, e.g. RM-11) -- and contains no timing
logic itself: it is told "escalation eligibility was reached, act now."

``on_threat_assessment()`` subscribes to the real ThreatAssessmentEvent bus
stream (per EVENT_CONTRACTS.md's documented Incident Service consumer entry)
purely for metadata (weapon/uniform/zone/rule_id, for ``threat_summary``) and
track-lost bookkeeping ("last seen") -- never for escalation timing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.incident import Incident
from apps.api.app.repositories.incident import IncidentRepository
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import EventBus
from shared.events.payloads import IncidentCreatedPayload, IncidentUpdatedPayload
from shared.events.types import IncidentCreatedEvent, IncidentUpdatedEvent, ThreatAssessmentEvent

TRACK_LOST_SECONDS = 10.0

TrackKey = tuple[uuid.UUID, int]


@dataclass
class _TrackMetadata:
    """Most recent classification detail for a track, cached from
    ThreatAssessmentEvent -- used to populate a new incident's
    ``threat_summary`` (docs/DATABASE_SCHEMA.md's example shape)."""

    weapon_type: str
    uniform: str
    zone: str
    rule_id: str


class IncidentService:
    """Owns incident creation, dedup, and track-lost auto-close."""

    def __init__(self, session: AsyncSession, bus: EventBus | None = None) -> None:
        self._session = session
        self._repo = IncidentRepository(session)
        self._bus = bus
        self._metadata: dict[TrackKey, _TrackMetadata] = {}
        self._last_seen: dict[TrackKey, datetime] = {}

    async def on_threat_assessment(self, event: ThreatAssessmentEvent) -> None:
        """Cache metadata and last-seen for track bookkeeping.

        No escalation-timing decisions are made here -- this only supports
        ``handle_escalation()``'s threat_summary population and
        ``sweep_track_lost()``'s absence detection.
        """
        key = (event.payload.camera_id, event.payload.track_id)
        self._metadata[key] = _TrackMetadata(
            weapon_type=event.payload.weapon_type.value,
            uniform=event.payload.uniform.value,
            zone=event.payload.zone.value,
            rule_id=event.payload.rule_id,
        )
        self._last_seen[key] = event.timestamp

    async def handle_escalation(
        self,
        *,
        camera_id: uuid.UUID,
        track_id: int,
        threat_level: ThreatLevel,
        reason: str,
        timestamp: datetime,
    ) -> Incident:
        """Create (or return the existing) active incident for this track.

        Called directly, in-process, when escalation eligibility has already
        been determined elsewhere (Threat Engine). Contains no debounce or
        sustained-duration logic of its own -- idempotent create-or-return.
        """
        existing = await self._repo.get_active_for_track(camera_id, track_id)
        if existing is not None:
            return existing

        metadata = self._metadata.get((camera_id, track_id))
        threat_summary = (
            {
                "weapon": metadata.weapon_type,
                "uniform": metadata.uniform,
                "zone": metadata.zone,
                "rule_id": metadata.rule_id,
            }
            if metadata is not None
            else {}
        )

        incident = Incident(
            camera_id=camera_id,
            track_id=track_id,
            incident_type=IncidentType.THREAT,
            threat_level=threat_level,
            status=IncidentStatus.NEW,
            threat_summary=threat_summary,
        )

        try:
            await self._repo.add(incident)
        except IntegrityError:
            # Lost a create race to another concurrent caller -- the dedup
            # constraint (ADR-025) guarantees exactly one active incident
            # exists now; fall back to it rather than failing.
            await self._session.rollback()
            existing = await self._repo.get_active_for_track(camera_id, track_id)
            assert existing is not None
            return existing

        await self._publish_created(incident)

        # NEW -> ACTIVE is system-owned and immediate (INCIDENT_LIFECYCLE.md --
        # ACTIVE's entry condition is "incident created", no separate trigger).
        await self._transition(incident, IncidentStatus.ACTIVE)

        return incident

    async def sweep_track_lost(self, now: datetime) -> list[Incident]:
        """Close (RESOLVE) any active incident whose track hasn't produced a
        ThreatAssessmentEvent in over TRACK_LOST_SECONDS (ADR-025)."""
        closed: list[Incident] = []
        for key, last_seen in list(self._last_seen.items()):
            if (now - last_seen).total_seconds() <= TRACK_LOST_SECONDS:
                continue
            del self._last_seen[key]
            camera_id, track_id = key
            incident = await self._repo.get_active_for_track(camera_id, track_id)
            if incident is None:
                continue
            incident.resolved_at = now
            await self._transition(incident, IncidentStatus.RESOLVED)
            closed.append(incident)
        return closed

    async def _transition(self, incident: Incident, new_status: IncidentStatus) -> None:
        old_status = incident.status
        incident.status = new_status
        await self._session.flush()
        if old_status != new_status:
            await self._publish_updated(incident, old_status, new_status)

    async def _publish_created(self, incident: Incident) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            IncidentCreatedEvent(
                event_type="IncidentCreatedEvent",
                source="incident_service",
                payload=IncidentCreatedPayload(
                    incident_id=incident.id,
                    camera_id=incident.camera_id,
                    track_id=incident.track_id,
                    incident_type=incident.incident_type,
                    threat_level=incident.threat_level,
                    status=incident.status,
                ),
            )
        )

    async def _publish_updated(
        self, incident: Incident, old_status: IncidentStatus, new_status: IncidentStatus
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            IncidentUpdatedEvent(
                event_type="IncidentUpdatedEvent",
                source="incident_service",
                payload=IncidentUpdatedPayload(
                    incident_id=incident.id,
                    old_status=old_status,
                    new_status=new_status,
                ),
            )
        )
