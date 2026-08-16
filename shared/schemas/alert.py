"""Alert API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md
  - Real-Time Event Streams / Alert Events section (/ws/alerts, ADR-029)
  - docs/EVENT_CONTRACTS.md's AlertRaisedEvent

Every incident raises an alert regardless of severity (unlike alarms,
which are HIGH/FIRE-only per ADR-026) -- see
services/alert_service/service.py's module docstring.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shared.constants.threat_levels import ThreatLevel


class AlertSchema(BaseModel):
    """WebSocket message body for the ``/ws/alerts`` channel.

    Matches ``docs/EVENT_CONTRACTS.md``'s ``AlertRaisedEvent`` payload
    shape.
    """

    alert_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    severity: ThreatLevel
    channels: list[str]
    deduplicated: bool
