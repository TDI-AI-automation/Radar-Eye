# Frontend Backend Contracts

## Purpose

Define all backend interfaces required by the Radar Eye Command frontend.

The frontend repository:

https://github.com/CodeHub1443/radar-eye-command

must consume only these approved contracts.

---

# API Standards

Base Path:

/api/v1

Authentication:

Session / Token

Future:

LDAP / Active Directory

Response Format:

{
  "success": true,
  "data": {}
}

---

# Live Monitoring

## REST

GET /cameras

GET /threats/active

GET /incidents/open

## WebSocket

/ws/threats

/ws/incidents

/ws/camera-health

Purpose:

Real-time operational monitoring.

---

# Incident Center

## REST

GET /incidents

GET /incidents/{incident_id}

PATCH /incidents/{incident_id}

GET /incidents/{incident_id}/events

GET /incidents/{incident_id}/evidence

Purpose:

Incident investigation and management.

---

# Tactical Map

## REST

GET /cameras

GET /threats/active

GET /incidents/open

## WebSocket

/ws/tracking

/ws/incidents

Purpose:

Operational situational awareness.

---

# Camera Management

## REST

GET /cameras

GET /cameras/{camera_id}

PATCH /cameras/{camera_id}

GET /cameras/{camera_id}/health

GET /cameras/{camera_id}/calibration

Purpose:

Camera administration.

---

# Analytics

## REST

GET /analytics/threats

GET /analytics/incidents

GET /analytics/cameras

GET /analytics/system

Purpose:

Historical analytics.

---

# System Health

## REST

GET /health/system

GET /health/gpu

GET /health/storage

GET /health/recording

GET /health/cameras

Purpose:

Operational monitoring.

---

# Settings

## REST

GET /config

PATCH /config

GET /users

PATCH /users/{user_id}

Purpose:

System administration.

Notes:

`PATCH /users` (no identifier) was a documentation error -- corrected to
`PATCH /users/{user_id}`, matching every other mutating route in this
contract (each takes a path identifier; there is no collection-level PATCH
anywhere else in this document). Scoped to updating one user's `role`
only -- `username`/`password_hash` are not exposed through this route.

`GET`/`PATCH /config` are not yet implemented (docs/OPEN_QUESTIONS.md
Q-014) -- no persistence model for system configuration is defined in
`docs/DATABASE_SCHEMA.md` or `docs/DOMAIN_MODEL.md` yet.

---

# Threat Review Center

## REST

GET /reviews

GET /reviews/{review_id}

PATCH /reviews/{review_id}

POST /reviews/{review_id}/confirm-military

POST /reviews/{review_id}/confirm-civilian

POST /reviews/{review_id}/escalate

POST /reviews/{review_id}/dismiss

Purpose:

Human review workflow.

---

# Calibration Center

## REST

GET /calibration/cameras

POST /calibration/start

POST /calibration/validate

GET /calibration/results

GET /calibration/{camera_id}

Purpose:

Distance estimation management.

---

# Evidence Viewer

## REST

GET /evidence

GET /evidence/{evidence_id}

GET /recordings

GET /recordings/{recording_id}

GET /recordings/{recording_id}/download

GET /snapshots/{snapshot_id}

GET /snapshots/{snapshot_id}/download

Purpose:

Evidence retrieval.

---

# Real-Time Event Streams

## Threat Events

WebSocket:

/ws/threats

Event:

ThreatAssessmentEvent

---

## Incident Events

WebSocket:

/ws/incidents

Events:

- IncidentCreatedEvent
- IncidentUpdatedEvent

---

## Human Review Events

WebSocket:

/ws/reviews

Event:

HumanReviewItemCreatedEvent

---

## Alarm Events

WebSocket:

/ws/alarms

Event:

AlarmRequestedEvent

---

## Camera Events

WebSocket:

/ws/camera-health

Events:

- CameraDisconnectedEvent
- SystemEvent

---

# Frontend Event Models

## ThreatAssessmentEvent

{
  "camera_id": "uuid",
  "track_id": 123,
  "weapon_type": "ranged_lethal",
  "uniform": "civilian",
  "zone": "zone_1",
  "threat_level": "HIGH"
}

---

## IncidentCreatedEvent

{
  "incident_id": "uuid",
  "camera_id": "uuid",
  "track_id": 123,
  "status": "NEW"
}

---

## HumanReviewItemCreatedEvent

{
  "review_item_id": "uuid",
  "camera_id": "uuid",
  "track_id": 123,
  "reason": "uniform_unknown"
}

---

## AlarmRequestedEvent

{
  "incident_id": "uuid",
  "camera_id": "uuid",
  "threat_level": "HIGH"
}

---

# Architecture Constraints

Mandatory:

- REST for retrieval
- WebSocket for real-time events

Avoid:

- Polling where practical

Reason:

Reduce latency and backend load.