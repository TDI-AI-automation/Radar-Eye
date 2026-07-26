"""Camera API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Camera Management and
  Live Monitoring sections.
  GET /cameras, GET /cameras/{camera_id}, GET /cameras/{camera_id}/health
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from shared.events.payloads import SystemEventSeverity

CameraConnectionStatus = Literal["CONNECTED", "DISCONNECTED", "RECONNECTING"]


class CameraHealthSchema(BaseModel):
    """Per-camera health metrics surfaced by the System Health Agent.

    Returned by ``GET /cameras/{camera_id}/health``. **Not** the
    ``/ws/camera-health`` WebSocket message body -- that channel forwards
    ``CameraDisconnectedEvent``/``SystemEvent`` (disconnect notifications
    and operational log events), not ongoing health metrics like this
    schema. Corrected during the RM-12 Architecture Readiness Review, which
    had initially listed this schema against that channel in error -- see
    ``CameraDisconnectedSchema``/``SystemEventSchema`` below for the actual
    ``/ws/camera-health`` shapes.
    """

    camera_id: uuid.UUID
    status: CameraConnectionStatus
    fps: float | None = None
    """Current decoded frames per second; None when disconnected."""
    last_frame_age_seconds: float | None = None
    """Seconds since the last frame was received; None when disconnected."""


class CameraDisconnectedSchema(BaseModel):
    """WebSocket message body for ``/ws/camera-health`` --
    CameraDisconnectedEvent (from ``shared.events.payloads.
    CameraDisconnectedPayload``, RM-12 Phase 5 -- no frontend-facing schema
    existed for this internal payload before)."""

    camera_id: uuid.UUID
    reason: str


class SystemEventSchema(BaseModel):
    """WebSocket message body for ``/ws/camera-health`` -- SystemEvent
    (from ``shared.events.payloads.SystemEventPayload``, RM-12 Phase 5)."""

    severity: SystemEventSeverity
    source_component: str
    message: str


class CameraSchema(BaseModel):
    """Full camera representation.

    Returned by ``GET /cameras`` (list) and ``GET /cameras/{camera_id}``.
    RTSP credentials are excluded from API responses (stored encrypted,
    per RM-03 / DATABASE_SCHEMA.md).
    """

    camera_id: uuid.UUID
    name: str
    location: str | None = None
    status: CameraConnectionStatus
    created_at: datetime
    updated_at: datetime


class CameraUpdateRequestSchema(BaseModel):
    """Body of ``PATCH /cameras/{camera_id}`` -- partial update, every field
    optional. RTSP credentials are never updated through this route (they
    live in ``camera_stream_profiles``, encrypted -- out of scope here)."""

    name: str | None = None
    location: str | None = None
    status: CameraConnectionStatus | None = None


class CameraCalibrationSchema(BaseModel):
    """Ground-plane calibration for a camera (ADR-016).

    Returned by ``GET /cameras/{camera_id}/calibration`` and the
    Calibration Center's ``GET /calibration/{camera_id}`` /
    ``GET /calibration/results`` -- calibration is append-only
    (docs/DATABASE_SCHEMA.md), so this always represents one specific
    calibration record, never a mutable "current calibration" object.
    """

    calibration_id: uuid.UUID
    camera_id: uuid.UUID
    homography_matrix: dict[str, Any]
    reference_points: dict[str, Any]
    calibrated_by: str | None = None
    created_at: datetime
