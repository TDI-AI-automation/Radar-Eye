"""Event payload models.

Source: docs/EVENT_CONTRACTS.md — individual event sections.

One Pydantic model per event type.  All payloads are frozen (immutable) to
enforce the EVENT_CONTRACTS.md rule that events cannot be modified after
publication.

Fields use the canonical shared enums from ``shared.constants`` wherever a
field value is constrained to a known set.  Free-form string fields (e.g.
``reason``, ``message``) remain plain ``str``.

Events defined here (13 total, matching EVENT_CONTRACTS.md):
  - ObservationEventPayload
  - ThreatAssessmentPayload
  - HumanReviewItemCreatedPayload
  - IncidentCreatedPayload
  - IncidentUpdatedPayload
  - AlarmEligiblePayload
  - AlarmRequestedPayload
  - AlertRaisedPayload
  - SnapshotCreatedPayload
  - ClipCreatedPayload
  - CameraDisconnectedPayload
  - CalibrationUpdatedPayload
  - SystemEventPayload
"""

from __future__ import annotations

import uuid
from datetime import datetime
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
# ObservationEvent
# Producer: AI Runtime
# Consumers: any subsystem (ADR-029 — AI Runtime is unaware of its consumers)
# ---------------------------------------------------------------------------


class ObservationExtension(_FrozenPayload):
    """Common base for every ObservationDetection extension type.

    Empty today (no shared fields) — exists so each extension type below
    is part of one polymorphic family from the start, rather than an
    unrelated standalone model, ahead of a second extension type actually
    shipping.
    """


class PoseExtension(ObservationExtension):
    """Reserved for a future pose-estimation model. No fields yet."""


class OcrExtension(ObservationExtension):
    """Reserved for a future OCR/LPR model. No fields yet."""


class SegmentationExtension(ObservationExtension):
    """Reserved for a future segmentation model. No fields yet."""


class EmbeddingExtension(ObservationExtension):
    """Reserved for a future ReID/face-embedding model. No fields yet."""


class ObservationExtensions(_FrozenPayload):
    """Namespaced, typed extension point for ObservationDetection.

    Extensible, not schema-less: a new CV capability (pose, OCR,
    segmentation, embeddings, ...) is added as a new named, typed field
    here — never as an arbitrary key in an untyped dict. All-`None` by
    default; nothing populates any of these in Phase 3 (no pose/OCR/
    segmentation/embedding model exists yet).
    """

    pose: PoseExtension | None = None
    ocr: OcrExtension | None = None
    segmentation: SegmentationExtension | None = None
    embedding: EmbeddingExtension | None = None


class BoundingBoxPayload(_FrozenPayload):
    """Payload mirror of
    ``apps.deepstream.app.ai_runtime.observations.BoundingBox``."""

    left: float
    top: float
    width: float
    height: float


class ObservationDetection(_FrozenPayload):
    """One detected object within one ObservationEvent.

    ``detection_id`` identifies this detection within this one
    ObservationEvent only — it is not a tracking identifier and must
    never be reused across observations. ``track_id`` is temporal
    identity across frames/events; ``detection_id`` is event identity
    within one. Both are needed; they answer different questions.
    """

    detection_id: uuid.UUID
    track_id: int | None
    class_id: int
    label: str
    confidence: float
    bbox: BoundingBoxPayload
    secondary_label: str | None = None
    extensions: ObservationExtensions | None = None


class ObservationEventPayload(_FrozenPayload):
    """Payload for ObservationEvent.

    The canonical output contract of AI Runtime — observations only,
    never a decision. Contains only directly observable facts produced
    by computer vision; never inferred, interpreted, or policy-derived
    state (threat level, incident level, alarm decision, authorization
    result, rule violation, etc.) — those belong exclusively to
    downstream services.

    ``observation_id`` is generated exactly once by AI Runtime,
    immediately after metadata extraction and before this payload is
    constructed (never regenerated if the event is rebuilt) — the
    stable identifier every downstream event (IncidentEvent,
    AlertEvent, EvidenceEvent, RecordingEvent, AuditEvent, etc.)
    references instead of inventing its own, since ``frame_num`` alone
    can reset after a reconnect and frames can be dropped.

    Append-only for the lifetime of the product: existing fields are
    never repurposed (e.g. ``label`` must never silently shift meaning)
    — new semantics arrive as additive fields or a new schema version.
    """

    observation_id: uuid.UUID
    camera_id: uuid.UUID
    frame_num: int
    frame_timestamp: datetime
    detections: list[ObservationDetection]


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
# AlarmEligibleEvent (ADR-029 Phase 6)
# Producer: Incident Service
# Consumers: Alert Service
# ---------------------------------------------------------------------------


class AlarmEligiblePayload(_FrozenPayload):
    """Payload for AlarmEligibleEvent.

    Incident Service observes Threat Engine's own ``EscalationSignalType.
    ALARM_ELIGIBLE`` (HIGH sustained >=3s, or FIRE immediate -- a distinct,
    later threshold than ``INCIDENT_ELIGIBLE``'s 1s, per ADR-021's sustained-
    duration timing, which stays exclusively Threat Engine's) and republishes
    it onto the bus in this payload, since that signal is otherwise never
    serialized -- it's Threat Engine's internal return value, consumed
    synchronously inside Incident Service's own process. Alert Service (a
    separate process per ADR-029) has no other way to learn a track crossed
    this specific threshold: ``IncidentCreatedEvent``/``IncidentUpdatedEvent``
    carry no sustained-duration field. Mirrors ``ThreatAssessmentEvent``'s own
    precedent of re-exposing an internally-observed Threat Engine signal.
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    threat_level: ThreatLevel
    reason: str
    """Short description of the alarm trigger (e.g. "sustained_high_threat")."""


# ---------------------------------------------------------------------------
# AlarmRequestedEvent
# Producer: Alert Service (amended by ADR-029 -- was Threat Engine; Alert
# Service now owns the HIGH/FIRE eligibility rule per ADR-026)
# Consumers: Hardware Action Service, API Service
# ---------------------------------------------------------------------------


class AlarmRequestedPayload(_FrozenPayload):
    """Payload for AlarmRequestedEvent.

    Only emitted for HIGH and FIRE threat levels (ADR-026), triggered by
    Alert Service upon receiving ``AlarmEligibleEvent`` (above).
    """

    incident_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    threat_level: ThreatLevel
    reason: str
    """Short description of the alarm trigger (e.g. "sustained_high_threat")."""


# ---------------------------------------------------------------------------
# AlertRaisedEvent (ADR-029 Phase 6)
# Producer: Alert Service
# Consumers: API Service, Frontend
# ---------------------------------------------------------------------------


class AlertRaisedPayload(_FrozenPayload):
    """Payload for AlertRaisedEvent.

    Distinct from AlarmRequestedEvent above: this carries the alert/
    notification decision (severity, dedup state) for every incident
    Alert Service is notified of, not just HIGH/FIRE ones -- an operator
    is notified of every incident; only HIGH/FIRE additionally produces
    an AlarmRequestedEvent for physical hardware actuation.
    """

    alert_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    severity: ThreatLevel
    channels: list[str]
    """Notification channels this alert was raised on. Always includes
    "ui" (delivered via the /ws/alerts WebSocket channel, apps.api's
    existing bridge -- no separate delivery mechanism needed for it).
    SMS/Email/WhatsApp (docs/OPEN_QUESTIONS.md Q-005) are a documented,
    unimplemented extension seam (services/alert_service/notification.py)
    -- no external provider is configured in this air-gapped deployment,
    so no channel beyond "ui" is ever populated yet."""
    deduplicated: bool
    """True when this event corresponds to a repeat notification for an
    already-active alert on the same incident, rather than a new one."""


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
# CameraRegisteredEvent
# Producer: Camera Registry (RM-12)
# Consumers: DeepStream (Camera Runtime -- future: reacts to new/changed
#   cameras instead of only loading the roster once at startup, RM-12
#   §6 "Dynamic source management"), Frontend (WS)
# ---------------------------------------------------------------------------


class CameraRegisteredPayload(_FrozenPayload):
    """Payload for CameraRegisteredEvent."""

    camera_id: uuid.UUID
    name: str


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
