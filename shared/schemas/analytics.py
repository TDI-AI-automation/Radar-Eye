"""Analytics API schemas -- RM-12 Phase 3.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Analytics section.
Authority: docs/RM-12_ARCHITECTURE.md §4 -- these are straightforward
repository-query aggregations over existing tables, not a new analytics
computation engine (explicitly out of scope for RM-12).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class ThreatAnalyticsSchema(BaseModel):
    """Returned by ``GET /analytics/threats``."""

    counts_by_threat_level: dict[str, int]


class IncidentAnalyticsSchema(BaseModel):
    """Returned by ``GET /analytics/incidents``."""

    total: int
    counts_by_status: dict[str, int]


class CameraAnalyticsSchema(BaseModel):
    """Returned by ``GET /analytics/cameras``."""

    total_cameras: int
    incident_counts_by_camera: dict[uuid.UUID, int]


class SystemAnalyticsSchema(BaseModel):
    """Returned by ``GET /analytics/system``."""

    total_cameras: int
    total_incidents: int
    total_reviews: int
    total_audit_entries: int
