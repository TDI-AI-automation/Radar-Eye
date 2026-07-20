"""Incident Service -- incident lifecycle, dedup, and persistence.

Source: docs/INCIDENT_LIFECYCLE.md. Authority: ADR-024, ADR-025.
"""

from __future__ import annotations

from services.incident_service.service import IncidentService

__all__ = ["IncidentService"]
