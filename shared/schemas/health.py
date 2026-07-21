"""Health monitoring API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — System Health section.
  GET /health/system, GET /health/gpu, GET /health/storage, GET /health/cameras
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

HealthStatus = Literal["healthy", "degraded", "unhealthy"]


class GPUHealthSchema(BaseModel):
    """GPU metric details surfaced from Jetson hardware or host monitoring."""

    utilization_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    temperature_celsius: float | None = None


class StorageHealthSchema(BaseModel):
    """Storage space metrics for evidence and recording storage targets."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float


class CameraHealthSummarySchema(BaseModel):
    """Aggregated camera connection status count."""

    total_cameras: int
    connected_count: int
    disconnected_count: int
    reconnecting_count: int
    stalled_count: int = 0


class SystemHealthSchema(BaseModel):
    """Overall system health metrics and component statuses.

    Returned by ``GET /health/system``.
    """

    status: HealthStatus
    timestamp: datetime
    gpu: GPUHealthSchema | None = None
    storage: StorageHealthSchema | None = None
    cameras: CameraHealthSummarySchema
    components: dict[str, str]
    """Map of subsystem/component names to state
    (e.g. {"database": "healthy", "event_bus": "healthy"})."""
