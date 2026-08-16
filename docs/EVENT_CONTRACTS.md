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

# ObservationEvent

Added by ADR-029 (Phase 3/4). The sole hand-off point between AI
Runtime (`apps/deepstream`) and every downstream business service —
see `docs/DEEPSTREAM_PIPELINE_SPEC.md` Stage 5.6. Payload shape mirrors
the existing `FrameObservation` / `DetectionObservation` /
`TrackObservation` domain objects (ADR-027), now serialized onto the
bus instead of passed in-process. Named for what it contains
(observations), not who produced it — if a future perception engine
replaces DeepStream, only the Producer field below changes.

**Observations only, never decisions (ADR-029 Governing Principle):**
this payload may only contain measurements — detections, tracks,
classifications, confidence, bounding boxes, timestamps, `camera_id`,
`frame_num`. It must never contain a decision field (threat level,
alert, incident, "intruder," escalation, "hostile," or similar) — those
are computed downstream, by the service that owns that decision.

`observation_id` is generated exactly once by AI Runtime, immediately
after metadata extraction and before this payload is constructed --
the stable identifier every downstream event (`IncidentEvent`,
`AlertEvent`, `EvidenceEvent`, etc., built in later phases) references
instead of inventing its own. Each detection's `detection_id` likewise
identifies that detection within this one event only -- it is not a
tracking identifier and is never reused across observations (`track_id`
is temporal identity across frames/events; `detection_id` is event
identity within one).

`extensions` is a typed, namespaced extension point (`pose`/`ocr`/
`segmentation`/`embedding`, all optional) reserved for future CV
outputs -- not a schema-less dict. None are populated yet (no such
model exists in this repository today).

## Producer

AI Runtime

## Consumers

- Incident Service
- Evidence Service

## Payload

{
  "observation_id": "uuid",
  "camera_id": "uuid",
  "frame_num": 123,
  "frame_timestamp": "ISO8601",
  "detections": [
    {
      "detection_id": "uuid",
      "track_id": 7,
      "class_id": 0,
      "label": "person",
      "confidence": 0.95,
      "bbox": {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0},
      "secondary_label": "civilian",
      "extensions": null
    }
  ]
}

---

# ThreatAssessmentEvent

## Producer

Threat Engine (executes inside the Incident Service process as of
ADR-029 — the rule table and payload shape are unchanged from ADR-015;
only where it runs changed)

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

# AlarmEligibleEvent

Added by ADR-029 (Phase 6), during implementation -- not explicitly named
in ADR-029's own decision text, which only says Alert Service "consumes
Incident events (IncidentCreatedEvent/IncidentUpdatedEvent)". Neither of
those two events carries the sustained-duration signal Threat Engine
computes (INCIDENT_ELIGIBLE at HIGH sustained >=1s vs. the separate,
later ALARM_ELIGIBLE at HIGH sustained >=3s, or FIRE immediate -- ADR-021
keeps this timing exclusively Threat Engine's) -- without this event,
Alert Service would have no way to reproduce the existing, hardware-
validated alarm-eligibility timing. Incident Service already observes
Threat Engine's ALARM_ELIGIBLE signal internally (it always has, to
decide whether to also request an incident); this event just republishes
that observation onto the bus, the same pattern ThreatAssessmentEvent
already uses for a different internally-observed Threat Engine signal.

## Producer

Incident Service

## Consumers

- Alert Service

## Payload

{
  "incident_id": "uuid",
  "camera_id": "uuid",
  "track_id": 123,
  "threat_level": "HIGH",
  "reason": "sustained_high_threat"
}

---

# AlarmRequestedEvent

## Producer

Alert Service (amended by ADR-029 — was Threat Engine; Alert Service
now owns the HIGH/FIRE eligibility rule per ADR-026), triggered by
AlarmEligibleEvent above.

## Consumers

- Hardware Action Service (amended by ADR-029 — was Alarm Service, now
  split into Alert Service + Hardware Action Service)
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

# AlertRaisedEvent

Added by ADR-029 (Phase 6). Alert Service's own output, distinct from
`AlarmRequestedEvent` above — this carries the alert/notification
decision (severity, dedup, escalation state); `AlarmRequestedEvent`
remains the specific hardware-trigger request Alert Service also
produces when HIGH/FIRE eligibility is met.

## Producer

Alert Service

## Consumers

- API Service
- Frontend

## Payload

{
  "alert_id": "uuid",
  "incident_id": "uuid",
  "camera_id": "uuid",
  "severity": "HIGH",
  "channels": ["ui", "sms"],
  "deduplicated": false
}

---

# SnapshotCreatedEvent

## Producer

Evidence Service (amended by ADR-029 — was Recording Service; Evidence
Service now consumes `ObservationEvent` directly, independent of
Recording's postponement; the actual frame is requested/captured from
AI Streaming, never sent to Evidence Service by AI Runtime — see
`docs/DEEPSTREAM_PIPELINE_SPEC.md` Stage 8.7)

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

- Incident Service (amended by ADR-029 — was DeepStream; Distance
  Estimation now runs inside Incident Service, not DeepStream)

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

The Event Bus is transport only (ADR-029): publish, subscribe, deliver
— nothing else. No filtering, routing logic, business rules,
severity-based retries, transformation, or enrichment inside the bus.
Any of those belong to the consuming service.

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

- ObservationEvent
- ThreatAssessmentEvent
- HumanReviewItemCreatedEvent
- IncidentCreatedEvent
- IncidentUpdatedEvent
- AlarmEligibleEvent
- AlarmRequestedEvent
- AlertRaisedEvent
- SnapshotCreatedEvent
- ClipCreatedEvent