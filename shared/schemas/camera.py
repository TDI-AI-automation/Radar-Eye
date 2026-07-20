"""Camera API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Camera Management and
  Live Monitoring sections.
  GET /cameras, GET /cameras/{camera_id}, GET /cameras/{camera_id}/health

Also used on the Tactical Map (/ws/tracking) and camera-health channel
(/ws/camera-health).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CameraConnectionStatus = Literal["CONNECTED", "DISCONNECTED", "RECONNECTING"]


class CameraHealthSchema(BaseModel):
    """Per-camera health metrics surfaced by the System Health Agent.

    Returned by ``GET /cameras/{camera_id}/health`` and the
    ``/ws/camera-health`` WebSocket channel.
    """

    camera_id: uuid.UUID
    status: CameraConnectionStatus
    fps: float | None = None
    """Current decoded frames per second; None when disconnected."""
    last_frame_age_seconds: float | None = None
    """Seconds since the last frame was received; None when disconnected."""


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
