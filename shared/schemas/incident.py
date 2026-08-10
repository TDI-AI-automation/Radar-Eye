"""Incident-related API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md
  - Incident Center section (GET /incidents, GET /incidents/{id})
  - Frontend Event Models / IncidentCreatedEvent section
  - /ws/incidents WebSocket channel
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel


class IncidentSchema(BaseModel):
    """Full incident representation returned by ``GET /incidents/{incident_id}``.

    Used in Incident Center screens and evidence workflows.
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    incident_type: IncidentType
    threat_level: ThreatLevel
    status: IncidentStatus
    weapon_type: str | None
    """From the incident's ``threat_summary`` (services/incident_service --
    the weapon type observed when this incident was created). ``None`` for
    an incident created without a preceding ``ThreatAssessmentEvent``
    (e.g. a synthetic/manual escalation) rather than a fabricated value."""
    uniform: str | None
    """Same source as ``weapon_type`` -- the classified uniform."""
    zone: str | None
    """Same source as ``weapon_type`` -- the calibrated distance zone."""
    created_at: datetime
    updated_at: datetime


class IncidentSummarySchema(BaseModel):
    """Lightweight incident summary for list responses (``GET /incidents``).

    Omits timestamps to reduce payload size in list views. Includes
    ``weapon_type`` (unlike the other ``threat_summary`` fields) since
    that's exactly what an operator needs to triage the list at a glance,
    per THREAT_ENGINE_SPEC.md's auditability requirement.
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    threat_level: ThreatLevel
    status: IncidentStatus
    weapon_type: str | None


class IncidentCreatedSchema(BaseModel):
    """WebSocket message body for ``/ws/incidents`` — IncidentCreatedEvent.

    Matches the "Frontend Event Models / IncidentCreatedEvent" shape in
    FRONTEND_BACKEND_CONTRACTS.md.
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    status: IncidentStatus


class IncidentUpdatedSchema(BaseModel):
    """WebSocket message body for ``/ws/incidents`` — IncidentUpdatedEvent."""

    incident_id: uuid.UUID
    old_status: IncidentStatus
    new_status: IncidentStatus


class IncidentTransitionRequestSchema(BaseModel):
    """Body of ``PATCH /incidents/{incident_id}`` -- the only field an
    external caller may request a change to (docs/RM-12_ARCHITECTURE.md
    §3.3; services.incident_service.service.EXTERNALLY_REQUESTABLE_TRANSITIONS
    is the actual validation authority, not this schema)."""

    status: IncidentStatus


class IncidentEventSchema(BaseModel):
    """A single incident-lifecycle history entry.

    Returned by ``GET /incidents/{incident_id}/events`` (Incident Center) --
    thin wrap of the ``incident_events`` table (docs/DATABASE_SCHEMA.md).
    """

    event_id: uuid.UUID
    incident_id: uuid.UUID
    event_type: str
    event_payload: dict[str, Any]
    created_at: datetime
