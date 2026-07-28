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
"""Observed state (RM-12) -- written exclusively by Camera Runtime. Never
accepted from an operator-facing request body."""

CameraLifecycleState = Literal[
    "DRAFT", "TESTING", "VERIFIED", "OPERATIONAL", "MAINTENANCE", "DISABLED"
]
"""Desired/Persistent state (RM-12) -- written exclusively by Camera
Registry in response to an explicit operator action. Independent of
CameraConnectionStatus -- see apps.api.app.models.camera.Camera's
docstring for why these are two columns, not one enum."""


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
    lifecycle_state: CameraLifecycleState
    ai_enabled: bool
    recording_enabled: bool
    created_at: datetime
    updated_at: datetime


class CameraUpdateRequestSchema(BaseModel):
    """Body of ``PATCH /cameras/{camera_id}`` -- partial update, every field
    optional. RTSP credentials are never updated through this route (they
    live in ``camera_stream_profiles``, encrypted -- out of scope here).

    ``status`` (Observed state) is deliberately absent -- RM-12's Camera
    Runtime Ownership Refinement is explicit that connection status is
    never operator-settable; it previously appeared here in error. Use
    ``PATCH /cameras/{camera_id}/lifecycle`` for the one state an operator
    is actually allowed to change.

    ``ai_enabled``/``recording_enabled`` are Desired state -- Camera
    Registry persists the operator's intent only; this route performs no
    AI/recording behavior and never calls Camera Runtime, which is the one
    thing that actually observes and converges toward these flags.
    """

    name: str | None = None
    location: str | None = None
    ai_enabled: bool | None = None
    recording_enabled: bool | None = None


class CameraCreateRequestSchema(BaseModel):
    """Body of ``POST /cameras`` -- register a new camera. Combines the
    ``cameras`` and ``camera_stream_profiles`` rows in one request, matching
    the operator workflow's "Add Camera" step (RM-12 §2): a camera can't
    usefully exist without knowing how to connect to it. Mirrors
    ``scripts/siv_register_camera.py``'s existing shape (camera_id slug ->
    ``name``, rtsp_url/username/password/transport), which becomes a
    dev/bench convenience tool once this endpoint exists, not the only
    registration path.

    ``ai_enabled``/``recording_enabled`` default to ``False`` -- RM-12
    Design Principle 3 is explicit that adding a camera must never
    automatically start AI; the same "nothing happens until the operator
    explicitly asks" default applies symmetrically to recording.
    """

    name: str
    location: str | None = None
    rtsp_url: str
    username: str | None = None
    password: str | None = None
    transport: str = "tcp"
    ai_enabled: bool = False
    recording_enabled: bool = False


class CameraLifecycleUpdateRequestSchema(BaseModel):
    """Body of ``PATCH /cameras/{camera_id}/lifecycle``."""

    target_state: CameraLifecycleState


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
