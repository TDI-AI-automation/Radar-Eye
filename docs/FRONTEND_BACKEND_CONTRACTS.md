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

GET /cameras/brands

POST /cameras

GET /cameras/{camera_id}

PATCH /cameras/{camera_id}

DELETE /cameras/{camera_id}

GET /cameras/{camera_id}/health

GET /cameras/{camera_id}/calibration

Purpose:

Camera administration -- full operator workflow (register, edit, delete),
no curl/direct API calls required.

GET /cameras/brands lists every supported camera brand
(HIKVISION/DAHUA/UNIVIEW/AXIS/HANWHA) plus each one's default RTSP port
and stream path -- the Add/Edit Camera form's only source of these
defaults (apps.api.app.services.rtsp_url_generator).

POST /cameras registers a new camera (Camera Registry, RM-12) -- creates
both the camera record and its stream profile; Camera Runtime picks it
up and connects automatically, with no intermediate lifecycle state to
promote through. The operator supplies brand + IP + credentials +
port/stream (port/stream optional, defaulting per brand), never a raw
RTSP URL -- the backend generates it and stores only the generated,
encrypted URL.
model (hardware model number, e.g. "DS-2CD2143G0-I") is accepted and
stored alongside brand but is purely descriptive -- it plays no part in
RTSP URL generation.

PATCH /cameras/{camera_id} additionally accepts brand/model/ip_address/
port/username/password/transport/stream_path -- any of brand/ip_address/
port/username/password/transport/stream_path present regenerates and
re-encrypts the RTSP URL, merged with the camera's existing connection
info for whichever fields are omitted (e.g. changing only the IP keeps
the existing password). password is write-only and never appears in any
response or audit log entry.

DELETE /cameras/{camera_id} removes a camera and its own setup data
(stream profile, calibration history). Returns 409 if the camera has
existing incidents, review items, or recordings -- that history is never
cascade-deleted (Evidence Preservation); that history must be resolved
or exported first. Camera Runtime removes the corresponding pipeline
source and its entire runtime state automatically
(DesiredStateSynchronizer already reconciles toward "camera no longer in
Desired State" -- no separate signal needed). There are exactly two
operator controls for a camera: Connect/Disconnect, implicit through
registration/deletion, and AI Enable/Disable via PATCH
/cameras/{camera_id}'s `ai_enabled` field -- no intermediate lifecycle
state exists.

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