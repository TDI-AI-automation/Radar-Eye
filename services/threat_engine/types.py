"""Internal Threat Engine decision types.

``EscalationSignal`` is deliberately *not* ``IncidentCreatedEvent`` or
``AlarmRequestedEvent``. Those events require a real ``incident_id`` minted
by the Incident Service (RM-07), which does not exist yet, and
``AlarmRequestedEvent``'s documented producer (Threat Engine, per
EVENT_CONTRACTS.md) has no documented way to obtain that ID. Until RM-04
(event bus) and RM-07 exist and that hand-off is designed, the Threat Engine
surfaces escalation decisions as this internal signal; a future consumer is
responsible for turning ``INCIDENT_ELIGIBLE``/``ALARM_ELIGIBLE`` into the real
events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from shared.constants.threat_levels import ThreatLevel


class EscalationSignalType(str, Enum):
    """What threshold a track's sustained threat level just crossed."""

    INCIDENT_ELIGIBLE = "INCIDENT_ELIGIBLE"
    """HIGH sustained >=1s, MEDIUM sustained >=2s, or FIRE (immediate)."""

    ALARM_ELIGIBLE = "ALARM_ELIGIBLE"
    """HIGH sustained >=3s, or FIRE (immediate). Never fired for MEDIUM (ADR-026)."""


@dataclass(frozen=True)
class EscalationSignal:
    """A track crossing an incident- or alarm-eligibility threshold."""

    camera_id: uuid.UUID
    track_id: int
    signal_type: EscalationSignalType
    threat_level: ThreatLevel
    reason: str
