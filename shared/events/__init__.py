"""Shared events package.

Provides the event envelope, all payload models, and the concrete typed event
aliases used by every Radar Eye service.

Typical import patterns::

    # Full event type (envelope + payload)
    from shared.events import ThreatAssessmentEvent

    # Just the payload, when constructing programmatically
    from shared.events import ThreatAssessmentPayload

    # The generic envelope (advanced use)
    from shared.events import EventEnvelope
"""

from shared.events.envelope import EventEnvelope
from shared.events.payloads import (
    AlarmRequestedPayload,
    CalibrationUpdatedPayload,
    CameraDisconnectedPayload,
    ClipCreatedPayload,
    HumanReviewItemCreatedPayload,
    IncidentCreatedPayload,
    IncidentUpdatedPayload,
    SnapshotCreatedPayload,
    SystemEventPayload,
    ThreatAssessmentPayload,
)
from shared.events.types import (
    AlarmRequestedEvent,
    CalibrationUpdatedEvent,
    CameraDisconnectedEvent,
    ClipCreatedEvent,
    HumanReviewItemCreatedEvent,
    IncidentCreatedEvent,
    IncidentUpdatedEvent,
    SnapshotCreatedEvent,
    SystemEvent,
    ThreatAssessmentEvent,
)

__all__ = [
    # Envelope
    "EventEnvelope",
    # Payloads
    "AlarmRequestedPayload",
    "CalibrationUpdatedPayload",
    "CameraDisconnectedPayload",
    "ClipCreatedPayload",
    "HumanReviewItemCreatedPayload",
    "IncidentCreatedPayload",
    "IncidentUpdatedPayload",
    "SnapshotCreatedPayload",
    "SystemEventPayload",
    "ThreatAssessmentPayload",
    # Typed event aliases
    "AlarmRequestedEvent",
    "CalibrationUpdatedEvent",
    "CameraDisconnectedEvent",
    "ClipCreatedEvent",
    "HumanReviewItemCreatedEvent",
    "IncidentCreatedEvent",
    "IncidentUpdatedEvent",
    "SnapshotCreatedEvent",
    "SystemEvent",
    "ThreatAssessmentEvent",
]
