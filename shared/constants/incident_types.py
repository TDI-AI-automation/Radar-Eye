"""Incident type and status enums.

Source: docs/EVENT_CONTRACTS.md — IncidentCreatedEvent payload.
Cross-reference: docs/INCIDENT_LIFECYCLE.md, docs/DATABASE_SCHEMA.md (RM-03).

These enums are defined here (RM-02) because they are required for correct
typing of event payload models.  RM-03 (Database Migrations & Persistence
Layer) will reference these values when creating the incidents table.

No service may define its own IncidentType or IncidentStatus enum.
"""

from __future__ import annotations

from enum import Enum


class IncidentType(str, Enum):
    """The category of event that caused an incident to be created."""

    THREAT = "THREAT"
    """A sustained threat-level detection triggered incident creation."""


class IncidentStatus(str, Enum):
    """Lifecycle state of an incident.

    Transitions (per docs/INCIDENT_LIFECYCLE.md):
      NEW -> ACTIVE -> ACKNOWLEDGED -> CLOSED
    """

    NEW = "NEW"
    """Incident just created; not yet acknowledged by any operator."""

    ACTIVE = "ACTIVE"
    """Incident is ongoing — threat is still present."""

    ACKNOWLEDGED = "ACKNOWLEDGED"
    """An operator has reviewed the incident."""

    CLOSED = "CLOSED"
    """Incident resolved — track lost >10 s or operator-closed."""
