"""Alarm API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md
  - Real-Time Event Streams / Alarm Events section  (/ws/alarms)
  - Frontend Event Models / AlarmRequestedEvent

Alarms are only raised for HIGH and FIRE threat levels (ADR-026).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shared.constants.threat_levels import ThreatLevel


class AlarmSchema(BaseModel):
    """WebSocket message body for the ``/ws/alarms`` channel.

    Matches the "Frontend Event Models / AlarmRequestedEvent" shape in
    FRONTEND_BACKEND_CONTRACTS.md.
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    threat_level: ThreatLevel
    """Always HIGH (or implicitly FIRE-elevated HIGH) per ADR-026."""
