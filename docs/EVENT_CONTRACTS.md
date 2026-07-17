# Event Contracts

## Purpose

Define all events exchanged between system components.

All services must use these contracts.

---

# Event Envelope

Every event must contain:

{
  "event_id": "uuid",
  "event_type": "string",
  "source": "string",
  "timestamp": "ISO8601",
  "payload": {}
}

---

# ThreatAssessmentEvent

## Description

Generated after threat evaluation.

## Producer

Threat Engine

## Consumers

Incident Service
API Service

## Payload

{
  "camera_id": "cam01",
  "track_id": 123,
  "weapon_type": "ranged_lethal",
  "uniform": "civilian",
  "zone": "zone_1",
  "threat_level": "HIGH",
  "rule_id": "RANGED_LETHAL_ZONE_1"
}

---

# IncidentCreatedEvent

## Description

Generated when a new incident is created.

## Producer

Incident Service

## Consumers

Recording Service
API Service

## Payload

{
  "incident_id": "uuid",
  "camera_id": "cam01",
  "incident_type": "THREAT",
  "threat_level": "HIGH",
  "status": "NEW"
}

---

# IncidentUpdatedEvent

## Description

Generated when incident state changes.

## Producer

Incident Service

## Consumers

Recording Service
API Service

## Payload

{
  "incident_id": "uuid",
  "old_status": "ACTIVE",
  "new_status": "ACKNOWLEDGED"
}

---

# SnapshotCreatedEvent

## Description

Generated when a snapshot is stored.

## Producer

Recording Service

## Consumers

API Service

## Payload

{
  "snapshot_id": "uuid",
  "incident_id": "uuid",
  "camera_id": "cam01",
  "file_path": "/snapshots/cam01/..."
}

---

# ClipCreatedEvent

## Description

Generated when an event clip is stored.

## Producer

Recording Service

## Consumers

API Service

## Payload

{
  "recording_id": "uuid",
  "incident_id": "uuid",
  "camera_id": "cam01",
  "file_path": "/recordings/cam01/..."
}

---

# SystemEvent

## Description

System operational events.

## Producers

DeepStream
API
Recording Service

## Consumers

API Service
Frontend

## Payload

{
  "severity": "INFO",
  "source_component": "deepstream",
  "message": "Camera connected"
}

---

# CameraDisconnectedEvent

## Description

Camera connectivity failure.

## Producer

DeepStream

## Consumers

API Service

## Payload

{
  "camera_id": "cam01",
  "reason": "RTSP timeout"
}

---

# CalibrationUpdatedEvent

## Description

Calibration parameters changed.

## Producer

Calibration Service

## Consumers

DeepStream

## Payload

{
  "camera_id": "cam01",
  "calibration_id": "uuid"
}

---

# Event Transport Rules

Events are internal system messages.

Events are immutable.

Events cannot be modified after publication.

---

# Event Versioning

Every event contract must include:

{
  "schema_version": 1
}

Breaking changes require a new schema version.

---

# Event Naming Convention

<EventName>Event

Examples:

ThreatAssessmentEvent
IncidentCreatedEvent
IncidentUpdatedEvent
ClipCreatedEvent
SystemEvent