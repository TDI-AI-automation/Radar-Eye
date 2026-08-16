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

/ws/cameras/{camera_id}/video

Purpose:

Real-time operational monitoring.

## Live Video Delivery (ADR-032)

WS /ws/cameras/{camera_id}/video

Auth: `?token=` query parameter (browsers cannot set a WebSocket
handshake header) — same convention as every other `/ws/` channel in
this contract.

Message shape: no framing, no JSON envelope. Binary WebSocket frames
carrying a raw, continuous, low-latency MPEG-TS byte stream (H.264
video, AI overlays already burned in) — the same bytes `apps.deepstream`
writes to its own local `tcpserversink`, relayed verbatim.

Purpose:

Live video delivery. `apps.api` opens one dedicated TCP connection per
browser WebSocket connection to `apps.deepstream`'s per-camera
`tcpserversink` port (discovered via `camera_media_endpoints`,
`subsystem="live_stream"` — not a static config value, since the port
is assigned at runtime) and relays bytes in both directions, unmodified.
Not a network proxy to a DeepStream-hosted signaling server -- no
signaling of any kind is involved. The browser plays the stream via
`mpegts.js` (MSE-based; a plain `<video src>` cannot consume a raw
MPEG-TS byte stream, and native browser HLS/MSE APIs have no built-in
demuxer for it either).

Backend ownership (ADR-030/ADR-031/ADR-032):

DeepStream is the sole producer of this stream (Stage 5.5), and is
never touched by a browser requesting it — connecting, disconnecting,
refreshing, or how many browsers are watching, are all invisible to
DeepStream; `tcpserversink` accepts any number of simultaneous TCP
clients natively (GStreamer's own multi-client fan-out), so `apps.api`
opening more or fewer relay connections never reaches DeepStream's
pipeline at all. The frontend has no awareness of, and no dependency
on, which backend process is producing the bytes it's relaying --
`MpegtsVideoProvider`'s contract is exactly this one WebSocket channel,
nothing more. Measured glass-to-glass latency: ~0-1.2 seconds (replaces
ADR-031's HLS delivery, measured at ~10s and rejected as unacceptable
for real-time surveillance).

Channels:

Exactly one representation exists behind this channel: DeepStream's
AI-annotated output. There is no raw/non-AI channel (ADR-030) — Radar
Eye has no product requirement to show camera video independent of AI
processing. The browser never sees "raw," "annotated," or "AI" in this
contract; it only ever requests video for a camera and receives it.

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

DELETE /cameras/{camera_id} removes a camera, its own setup data (stream
profile, calibration history), and, per explicit product decision
(2026-08-10, overriding this document's/CLAUDE.md's original Evidence
Preservation default), its evidence history too: incidents (with their
events/snapshots/recordings) and human review items. Deletion is
unconditional -- an operator who deletes a camera gets it gone,
including its history; 409 is no longer a normal response (a defensive
fallback only, for any reference the service doesn't yet know to clean
up). Camera Runtime removes the corresponding pipeline source and its
entire runtime state automatically
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

## Alert Events (ADR-029, new)

WebSocket:

/ws/alerts

Event:

AlertRaisedEvent

---

## Alarm Events

WebSocket:

/ws/alarms

Event:

AlarmRequestedEvent

Note (ADR-029):

Producer is now Alert Service, not Threat Engine (see `docs/EVENT_CONTRACTS.md`) — this channel reflects Hardware Action Service's trigger requests, not a direct Threat Engine output.

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