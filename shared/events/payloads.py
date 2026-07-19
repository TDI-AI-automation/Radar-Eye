"""Event payload models.

Source: docs/EVENT_CONTRACTS.md — individual event sections.

One Pydantic model per event type.  All payloads are frozen (immutable) to
enforce the EVENT_CONTRACTS.md rule that events cannot be modified after
publication.

Fields use the canonical shared enums from ``shared.constants`` wherever a
field value is constrained to a known set.  Free-form string fields (e.g.
``reason``, ``message``) remain plain ``str``.

Events defined here (10 total, matching EVENT_CONTRACTS.md):
  - ThreatAssessmentPayload
  - HumanReviewItemCreatedPayload
  - IncidentCreatedPayload
  - IncidentUpdatedPayload
  - AlarmRequestedPayload
  - SnapshotCreatedPayload
  - ClipCreatedPayload
  - CameraDisconnectedPayload
  - CalibrationUpdatedPayload
  - SystemEventPayload
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from shared.constants.distance_zones import DistanceZone
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType


class _FrozenPayload(BaseModel):
    """Base class for all event payloads — frozen (immutable)."""

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# ThreatAssessmentEvent
# Producer: Threat Engine
# Consumers: Incident Service, API Service
# ---------------------------------------------------------------------------


class ThreatAssessmentPayload(_FrozenPayload):
    """Payload for ThreatAssessmentEvent.

    Emitted when the Threat Engine assigns a threat level to a track.
    ``rule_id`` makes the decision fully auditable (THREAT_ENGINE_SPEC.md —
    "Rule Auditability").
    """

    camera_id: uuid.UUID
    track_id: int
    weapon_type: WeaponType
    uniform: UniformClass
    zone: DistanceZone
    threat_level: ThreatLevel
    rule_id: str
    """Identifier of the rule row that produced this threat level
    (e.g. "RANGED_LETHAL_ZONE_1").  Required for auditability."""


# ---------------------------------------------------------------------------
# HumanReviewItemCreatedEvent
# Producer: Threat Engine
# Consumers: API Service, Frontend
# ---------------------------------------------------------------------------


class HumanReviewItemCreatedPayload(_FrozenPayload):
    """Payload for HumanReviewItemCreatedEvent.

    Emitted when a track's uniform classification is UNKNOWN and the subject
    is routed to the human review queue.
    """

    camera_id: uuid.UUID
    track_id: int
    reason: str
    """Short description of why review was triggered (e.g. "uniform_unknown")."""
    review_item_id: uuid.UUID


# ---------------------------------------------------------------------------
# IncidentCreatedEvent
# Producer: Incident Service
# Consumers: Recording Service, API Service
# ---------------------------------------------------------------------------


class IncidentCreatedPayload(_FrozenPayload):
    """Payload for IncidentCreatedEvent."""

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    incident_type: IncidentType
    threat_level: ThreatLevel
    status: IncidentStatus


# ---------------------------------------------------------------------------
# IncidentUpdatedEvent
# Producer: Incident Service
# Consumers: Recording Service, API Service
# ---------------------------------------------------------------------------


class IncidentUpdatedPayload(_FrozenPayload):
    """Payload for IncidentUpdatedEvent."""

    incident_id: uuid.UUID
    old_status: IncidentStatus
    new_status: IncidentStatus


# ---------------------------------------------------------------------------
# AlarmRequestedEvent
# Producer: Threat Engine
# Consumers: Alarm Service, API Service
# ---------------------------------------------------------------------------


class AlarmRequestedPayload(_FrozenPayload):
    """Payload for AlarmRequestedEvent.

    Only emitted for HIGH and FIRE threat levels (ADR-026).
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    threat_level: ThreatLevel
    reason: str
    """Short description of the alarm trigger (e.g. "sustained_high_threat")."""


# ---------------------------------------------------------------------------
# SnapshotCreatedEvent
# Producer: Recording Service
# Consumers: API Service
# ---------------------------------------------------------------------------


class SnapshotCreatedPayload(_FrozenPayload):
    """Payload for SnapshotCreatedEvent."""

    snapshot_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    file_path: str
    """Absolute path to the snapshot file on the local filesystem."""


# ---------------------------------------------------------------------------
# ClipCreatedEvent
# Producer: Recording Service
# Consumers: API Service
# ---------------------------------------------------------------------------


class ClipCreatedPayload(_FrozenPayload):
    """Payload for ClipCreatedEvent."""

    recording_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    file_path: str
    """Absolute path to the H.265 clip file on the local filesystem."""


# ---------------------------------------------------------------------------
# CameraDisconnectedEvent
# Producer: DeepStream (Video Ingestion Agent / System Health Agent)
# Consumers: API Service
# ---------------------------------------------------------------------------


class CameraDisconnectedPayload(_FrozenPayload):
    """Payload for CameraDisconnectedEvent."""

    camera_id: uuid.UUID
    reason: str
    """Human-readable disconnection cause (e.g. "RTSP timeout")."""


# ---------------------------------------------------------------------------
# CalibrationUpdatedEvent
# Producer: Calibration Service
# Consumers: DeepStream
# ---------------------------------------------------------------------------


class CalibrationUpdatedPayload(_FrozenPayload):
    """Payload for CalibrationUpdatedEvent.

    Signals DeepStream to reload the homography matrix for the given camera.
    """

    camera_id: uuid.UUID
    calibration_id: uuid.UUID


# ---------------------------------------------------------------------------
# SystemEvent
# Producers: DeepStream, API Service, Recording Service
# Consumers: API Service, Frontend
# ---------------------------------------------------------------------------

SystemEventSeverity = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class SystemEventPayload(_FrozenPayload):
    """Payload for SystemEvent.

    General-purpose operational log event surfaced to the frontend.
    """

    severity: SystemEventSeverity
    source_component: str
    """The producing service/component name (e.g. "deepstream", "recording")."""
    message: str
