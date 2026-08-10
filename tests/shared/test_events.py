"""Tests for shared/events — envelope, payloads, and round-trip serialisation.

Acceptance criteria (RM-02):
  - Every event type in EVENT_CONTRACTS.md has a corresponding typed alias.
  - Schema round-trips: construct → serialise to JSON → deserialise → equality.
  - Frozen models raise an error on mutation attempt.
  - event_id default is a valid UUID; timestamp default is UTC-aware.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.constants import (
    DistanceZone,
    IncidentStatus,
    IncidentType,
    ThreatLevel,
    UniformClass,
    WeaponType,
)
from shared.events import (
    AlarmRequestedEvent,
    AlarmRequestedPayload,
    CalibrationUpdatedEvent,
    CalibrationUpdatedPayload,
    CameraDisconnectedEvent,
    CameraDisconnectedPayload,
    ClipCreatedEvent,
    ClipCreatedPayload,
    EventEnvelope,
    HumanReviewItemCreatedEvent,
    HumanReviewItemCreatedPayload,
    IncidentCreatedEvent,
    IncidentCreatedPayload,
    IncidentUpdatedEvent,
    IncidentUpdatedPayload,
    ObservationEvent,
    ObservationEventPayload,
    SnapshotCreatedEvent,
    SnapshotCreatedPayload,
    SystemEvent,
    SystemEventPayload,
    ThreatAssessmentEvent,
    ThreatAssessmentPayload,
)
from shared.events.payloads import BoundingBoxPayload, ObservationDetection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAMERA_ID = uuid.uuid4()
_INCIDENT_ID = uuid.uuid4()
_REVIEW_ID = uuid.uuid4()
_SNAPSHOT_ID = uuid.uuid4()
_RECORDING_ID = uuid.uuid4()
_CALIBRATION_ID = uuid.uuid4()
_OBSERVATION_ID = uuid.uuid4()
_DETECTION_ID = uuid.uuid4()
_TRACK_ID = 42


def _make_observation_payload() -> ObservationEventPayload:
    return ObservationEventPayload(
        observation_id=_OBSERVATION_ID,
        camera_id=_CAMERA_ID,
        frame_num=123,
        frame_timestamp=datetime.now(timezone.utc),
        detections=[
            ObservationDetection(
                detection_id=_DETECTION_ID,
                track_id=_TRACK_ID,
                class_id=1,
                label="person",
                confidence=0.95,
                bbox=BoundingBoxPayload(left=1.0, top=2.0, width=3.0, height=4.0),
                secondary_label="civilian",
            )
        ],
    )


def _make_threat_payload() -> ThreatAssessmentPayload:
    return ThreatAssessmentPayload(
        camera_id=_CAMERA_ID,
        track_id=_TRACK_ID,
        weapon_type=WeaponType.RANGED_LETHAL,
        uniform=UniformClass.CIVILIAN,
        zone=DistanceZone.ZONE_1,
        threat_level=ThreatLevel.HIGH,
        rule_id="RANGED_LETHAL_ZONE_1",
    )


# ---------------------------------------------------------------------------
# Envelope defaults
# ---------------------------------------------------------------------------


class TestEventEnvelopeDefaults:
    def test_event_id_is_uuid(self) -> None:
        payload = _make_threat_payload()
        event = ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            payload=payload,
        )
        assert isinstance(event.event_id, uuid.UUID)

    def test_schema_version_default(self) -> None:
        payload = _make_threat_payload()
        event = ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            payload=payload,
        )
        assert event.schema_version == 1

    def test_timestamp_is_utc_aware(self) -> None:
        payload = _make_threat_payload()
        event = ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            payload=payload,
        )
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_envelope_is_frozen(self) -> None:
        payload = _make_threat_payload()
        event = ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            payload=payload,
        )
        with pytest.raises((ValidationError, TypeError)):
            event.source = "tampered"  # type: ignore[misc]

    def test_payload_is_frozen(self) -> None:
        payload = _make_threat_payload()
        with pytest.raises((ValidationError, TypeError)):
            payload.track_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Round-trip tests — one per event type
# ---------------------------------------------------------------------------


def _round_trip(event: EventEnvelope) -> EventEnvelope:  # type: ignore[type-arg]
    """Serialise to JSON, deserialise back using the same model type."""
    json_str = event.model_dump_json()
    data = json.loads(json_str)
    return type(event).model_validate(data)


class TestObservationRoundTrip:
    def test_round_trip(self) -> None:
        payload = _make_observation_payload()
        event = ObservationEvent(
            event_type="ObservationEvent",
            source="deepstream",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.observation_id == _OBSERVATION_ID
        assert restored.payload.camera_id == _CAMERA_ID
        assert restored.payload.frame_num == 123
        assert len(restored.payload.detections) == 1
        detection = restored.payload.detections[0]
        assert detection.detection_id == _DETECTION_ID
        assert detection.track_id == _TRACK_ID
        assert detection.label == "person"
        assert detection.secondary_label == "civilian"
        assert detection.bbox.left == 1.0
        assert detection.extensions is None

    def test_payload_is_frozen(self) -> None:
        payload = _make_observation_payload()
        with pytest.raises((ValidationError, TypeError)):
            payload.frame_num = 999  # type: ignore[misc]


class TestThreatAssessmentRoundTrip:
    def test_round_trip(self) -> None:
        payload = _make_threat_payload()
        event = ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.threat_level == ThreatLevel.HIGH
        assert restored.payload.rule_id == "RANGED_LETHAL_ZONE_1"
        assert restored.payload.weapon_type == WeaponType.RANGED_LETHAL
        assert restored.event_id == event.event_id


class TestHumanReviewItemCreatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = HumanReviewItemCreatedPayload(
            camera_id=_CAMERA_ID,
            track_id=_TRACK_ID,
            reason="uniform_unknown",
            review_item_id=_REVIEW_ID,
        )
        event = HumanReviewItemCreatedEvent(
            event_type="HumanReviewItemCreatedEvent",
            source="threat_engine",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.reason == "uniform_unknown"
        assert restored.payload.review_item_id == _REVIEW_ID


class TestIncidentCreatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = IncidentCreatedPayload(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            track_id=_TRACK_ID,
            incident_type=IncidentType.THREAT,
            threat_level=ThreatLevel.HIGH,
            status=IncidentStatus.NEW,
        )
        event = IncidentCreatedEvent(
            event_type="IncidentCreatedEvent",
            source="incident_service",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.status == IncidentStatus.NEW
        assert restored.payload.incident_id == _INCIDENT_ID


class TestIncidentUpdatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = IncidentUpdatedPayload(
            incident_id=_INCIDENT_ID,
            old_status=IncidentStatus.ACTIVE,
            new_status=IncidentStatus.ACKNOWLEDGED,
        )
        event = IncidentUpdatedEvent(
            event_type="IncidentUpdatedEvent",
            source="incident_service",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.old_status == IncidentStatus.ACTIVE
        assert restored.payload.new_status == IncidentStatus.ACKNOWLEDGED


class TestAlarmRequestedRoundTrip:
    def test_round_trip(self) -> None:
        payload = AlarmRequestedPayload(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            track_id=_TRACK_ID,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
        )
        event = AlarmRequestedEvent(
            event_type="AlarmRequestedEvent",
            source="threat_engine",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.threat_level == ThreatLevel.HIGH
        assert restored.payload.reason == "sustained_high_threat"


class TestSnapshotCreatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = SnapshotCreatedPayload(
            snapshot_id=_SNAPSHOT_ID,
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            file_path="/snapshots/camera_01/snap.jpg",
        )
        event = SnapshotCreatedEvent(
            event_type="SnapshotCreatedEvent",
            source="recording",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.file_path == "/snapshots/camera_01/snap.jpg"


class TestClipCreatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = ClipCreatedPayload(
            recording_id=_RECORDING_ID,
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            file_path="/recordings/camera_01/clip.mp4",
        )
        event = ClipCreatedEvent(
            event_type="ClipCreatedEvent",
            source="recording",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.recording_id == _RECORDING_ID


class TestCameraDisconnectedRoundTrip:
    def test_round_trip(self) -> None:
        payload = CameraDisconnectedPayload(
            camera_id=_CAMERA_ID,
            reason="RTSP timeout",
        )
        event = CameraDisconnectedEvent(
            event_type="CameraDisconnectedEvent",
            source="deepstream",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.reason == "RTSP timeout"


class TestCalibrationUpdatedRoundTrip:
    def test_round_trip(self) -> None:
        payload = CalibrationUpdatedPayload(
            camera_id=_CAMERA_ID,
            calibration_id=_CALIBRATION_ID,
        )
        event = CalibrationUpdatedEvent(
            event_type="CalibrationUpdatedEvent",
            source="calibration_service",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.calibration_id == _CALIBRATION_ID


class TestSystemEventRoundTrip:
    def test_round_trip(self) -> None:
        payload = SystemEventPayload(
            severity="INFO",
            source_component="deepstream",
            message="Camera connected",
        )
        event = SystemEvent(
            event_type="SystemEvent",
            source="deepstream",
            payload=payload,
        )
        restored = _round_trip(event)
        assert restored.payload.severity == "INFO"
        assert restored.payload.message == "Camera connected"

    def test_invalid_severity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SystemEventPayload(
                severity="NONSENSE",  # type: ignore[arg-type]
                source_component="deepstream",
                message="test",
            )


# ---------------------------------------------------------------------------
# Contract completeness — all 10 EVENT_CONTRACTS.md events are present
# ---------------------------------------------------------------------------


class TestContractCompleteness:
    """Every event type in EVENT_CONTRACTS.md must have a named alias."""

    EXPECTED_EVENT_TYPES = {
        "ObservationEvent",
        "ThreatAssessmentEvent",
        "HumanReviewItemCreatedEvent",
        "IncidentCreatedEvent",
        "IncidentUpdatedEvent",
        "AlarmRequestedEvent",
        "SnapshotCreatedEvent",
        "ClipCreatedEvent",
        "CameraDisconnectedEvent",
        "CalibrationUpdatedEvent",
        "SystemEvent",
    }

    def test_all_event_types_importable(self) -> None:
        import shared.events as events_module

        for name in self.EXPECTED_EVENT_TYPES:
            assert hasattr(
                events_module, name
            ), f"Missing event type: {name} — not exported from shared.events"
