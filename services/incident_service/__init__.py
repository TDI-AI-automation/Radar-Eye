"""Incident Service -- incident lifecycle, dedup, and persistence.

Source: docs/INCIDENT_LIFECYCLE.md. Authority: ADR-024, ADR-025.

AlarmService/AlarmAdapter (formerly re-exported here) moved to
services.alert_service.alarm under ADR-029 Phase 6 -- alarm-eligibility
ownership relocated from Incident Service to Alert Service, a separate
process per ADR-029's "no subsystem may call another independently-
deployed subsystem's internal logic directly" principle.
"""

from __future__ import annotations

from services.incident_service.service import IncidentService, IncidentTransitionError

__all__ = [
    "IncidentService",
    "IncidentTransitionError",
]
