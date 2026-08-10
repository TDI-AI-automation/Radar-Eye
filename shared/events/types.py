"""Concrete typed event aliases.

Combines EventEnvelope with each payload type to produce the named event
types that services import and publish/consume.

Usage::

    from shared.events.types import ThreatAssessmentEvent
    from shared.events.payloads import ThreatAssessmentPayload

    event = ThreatAssessmentEvent(
        event_type="ThreatAssessmentEvent",
        source="threat_engine",
        payload=ThreatAssessmentPayload(
            camera_id=...,
            track_id=1,
            weapon_type=WeaponType.RANGED_LETHAL,
            uniform=UniformClass.CIVILIAN,
            zone=DistanceZone.ZONE_1,
            threat_level=ThreatLevel.HIGH,
            rule_id="RANGED_LETHAL_ZONE_1",
        ),
    )
"""

from __future__ import annotations

from shared.events.envelope import EventEnvelope
from shared.events.payloads import (
    AlarmRequestedPayload,
    CalibrationUpdatedPayload,
    CameraDisconnectedPayload,
    CameraRegisteredPayload,
    ClipCreatedPayload,
    HumanReviewItemCreatedPayload,
    IncidentCreatedPayload,
    IncidentUpdatedPayload,
    ObservationEventPayload,
    SnapshotCreatedPayload,
    SystemEventPayload,
    ThreatAssessmentPayload,
)

# ---------------------------------------------------------------------------
# Public event type aliases
# ---------------------------------------------------------------------------

ObservationEvent = EventEnvelope[ObservationEventPayload]
ThreatAssessmentEvent = EventEnvelope[ThreatAssessmentPayload]
HumanReviewItemCreatedEvent = EventEnvelope[HumanReviewItemCreatedPayload]
IncidentCreatedEvent = EventEnvelope[IncidentCreatedPayload]
IncidentUpdatedEvent = EventEnvelope[IncidentUpdatedPayload]
AlarmRequestedEvent = EventEnvelope[AlarmRequestedPayload]
SnapshotCreatedEvent = EventEnvelope[SnapshotCreatedPayload]
ClipCreatedEvent = EventEnvelope[ClipCreatedPayload]
CameraDisconnectedEvent = EventEnvelope[CameraDisconnectedPayload]
CameraRegisteredEvent = EventEnvelope[CameraRegisteredPayload]
CalibrationUpdatedEvent = EventEnvelope[CalibrationUpdatedPayload]
SystemEvent = EventEnvelope[SystemEventPayload]

__all__ = [
    "AlarmRequestedEvent",
    "CalibrationUpdatedEvent",
    "CameraDisconnectedEvent",
    "CameraRegisteredEvent",
    "ClipCreatedEvent",
    "HumanReviewItemCreatedEvent",
    "IncidentCreatedEvent",
    "IncidentUpdatedEvent",
    "ObservationEvent",
    "SnapshotCreatedEvent",
    "SystemEvent",
    "ThreatAssessmentEvent",
]
