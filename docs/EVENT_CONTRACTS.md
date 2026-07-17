# Event Contracts

## Purpose

Define all events exchanged between system components.

All services must use these contracts.

---

# Event Envelope

Every event must contain:

{
  "event_id": "uuid",
  "schema_version": 1,
  "event_type": "string",
  "source": "string",
  "timestamp": "ISO8601",
  "payload": {}
}

---

# ThreatAssessmentEvent

## Producer

Threat Engine

## Consumers

- Incident Service
- API Service

## Payload

{
  "camera_id": "uuid",
  "track_id": 123,
  "weapon_type": "ranged_lethal",
  "uniform": "civilian",
  "zone": "zone_1",
  "threat_level": "HIGH",
  "rule_id": "RANGED_LETHAL_ZONE_1"
}

---

# HumanReviewItemCreatedEvent

## Producer

Threat Engine

## Consumers

- API Service
- Frontend

## Payload

{
  "camera_id": "uuid",
  "track_id": 123,
  "reason": "uniform_unknown",
  "review_item_id": "uuid"
}

---

# IncidentCreatedEvent

## Producer

Incident Service

## Consumers

- Recording Service
- API Service

## Payload

{
  "incident_id": "uuid",
  "camera_id": "uuid",
  "track_id": 123,
  "incident_type": "THREAT",
  "threat_level": "HIGH",
  "status": "NEW"
}

---

# IncidentUpdatedEvent

## Producer

Incident Service

## Consumers

- Recording Service
- API Service

## Payload

{
  "incident_id": "uuid",
  "old_status": "ACTIVE",
  "new_status": "ACKNOWLEDGED"
}

---

# AlarmRequestedEvent

## Producer

Threat Engine

## Consumers

- Alarm Service
- API Service

## Payload

{
  "incident_id": "uuid",
  "camera_id": "uuid",
  "track_id": 123,
  "threat_level": "HIGH",
  "reason": "sustained_high_threat"
}

---

# SnapshotCreatedEvent

## Producer

Recording Service

## Consumers

- API Service

## Payload

{
  "snapshot_id": "uuid",
  "incident_id": "uuid",
  "camera_id": "uuid",
  "file_path": "/snapshots/camera_01/file.jpg"
}

---

# ClipCreatedEvent

## Producer

Recording Service

## Consumers

- API Service

## Payload

{
  "recording_id": "uuid",
  "incident_id": "uuid",
  "camera_id": "uuid",
  "file_path": "/recordings/camera_01/file.mp4"
}

---

# CameraDisconnectedEvent

## Producer

DeepStream

## Consumers

- API Service

## Payload

{
  "camera_id": "uuid",
  "reason": "RTSP timeout"
}

---

# CalibrationUpdatedEvent

## Producer

Calibration Service

## Consumers

- DeepStream

## Payload

{
  "camera_id": "uuid",
  "calibration_id": "uuid"
}

---

# SystemEvent

## Producer

- DeepStream
- API Service
- Recording Service

## Consumers

- API Service
- Frontend

## Payload

{
  "severity": "INFO",
  "source_component": "deepstream",
  "message": "Camera connected"
}

---

# Event Transport Rules

Events are internal system messages.

Events are immutable.

Events cannot be modified after publication.

---

# Event Versioning

Every event must contain:

{
  "schema_version": 1
}

Breaking changes require a new schema version.

---

# Event Naming Convention

<EventName>Event

Examples:

- ThreatAssessmentEvent
- HumanReviewItemCreatedEvent
- IncidentCreatedEvent
- IncidentUpdatedEvent
- AlarmRequestedEvent
- SnapshotCreatedEvent
- ClipCreatedEvent