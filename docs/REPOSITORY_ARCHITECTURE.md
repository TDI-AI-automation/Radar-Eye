# Repository Architecture

## Purpose

Define the physical repository layout and ownership boundaries.

---

# Top-Level Structure

radar-eye/

├── apps/
├── services/
├── shared/
├── configs/
├── models/
├── scripts/
├── tests/
├── deployments/
├── docs/

---

# apps/

Contains executable applications.

## apps/deepstream

Pure CV engine (ADR-028, ADR-029). Camera ingestion is a separate
subsystem (`apps/ingestion`, ADR-028) and not this app's responsibility.

Responsibilities:

- DeepStream pipeline
- Detection
- Tracking
- Classification

Outputs:

- AI Streaming (annotated video)
- ObservationEvent (observations only — detections, tracks,
  classifications, confidence, bounding boxes, timestamps, camera_id,
  frame_id; never a decision. See `docs/EVENT_CONTRACTS.md`)

Explicitly not this app's responsibility (ADR-029):

- Distance estimation
- Threat evaluation
- Incident logic
- Alert logic
- Snapshot logic
- GPIO / siren / floodlight control
- Notification logic

---

## apps/api

Responsibilities:

- FastAPI backend
- REST APIs
- WebSocket APIs
- Authentication
- Database access

---

## apps/frontend

Responsibilities:

- Dashboard
- Incident management
- Playback
- Live monitoring

---

# services/

Contains business services.

## services/threat_engine

Responsibilities:

- Threat evaluation
- Threat scoring
- Threat rules

Input:

- Detection data
- Classification data
- Distance data

Output:

- Threat level

---

## services/incident_service

Consumes `ObservationEvent` (ADR-029) — invokes `services/calibration`
and `services/threat_engine` as part of its own event handling, then
runs incident lifecycle. This in-process library use (Incident Service
is the sole caller) is permitted under ADR-029's ownership rule; it is
not a cross-subsystem call. Superseded design: this orchestration used
to run in-process inside `apps/deepstream` (`ThreatEngineRuntimeAdapter`,
RM-11 Phase 2); ADR-029 moved it here.

Responsibilities:

- Distance estimation invocation (via services/calibration)
- Threat evaluation invocation (via services/threat_engine)
- Incident creation
- Incident updates
- Incident lifecycle management

---

## services/calibration

Responsibilities:

- Homography management
- Zone calculation
- Distance estimation support

Invoked by:

- services/incident_service (ADR-029 — was `apps/deepstream`)

---

## services/alert_service (ADR-029, new)

Consumes `IncidentCreatedEvent` / `IncidentUpdatedEvent`.

Responsibilities:

- Alert generation
- Severity
- Deduplication
- Escalation
- Operator notification (UI / SMS / Email / WhatsApp)
- HIGH/FIRE alarm-eligibility rule (ADR-026, relocated here)

Output:

- AlertRaisedEvent
- AlarmRequestedEvent

---

## services/hardware_action (ADR-029, new)

Consumes `AlertRaisedEvent`.

Responsibilities:

- GPIO relay
- Siren
- Floodlight
- PTZ preset
- Future physical integrations

Not this service's responsibility:

- Eligibility, dedup, escalation, or notification decisions (owned by
  services/alert_service)

---

## services/evidence (ADR-029, new)

Consumes `ObservationEvent` directly — not gated on Incident Service or
Alert Service state. Metadata-only in: no frame data is sent to this
service by AI Runtime. When a full frame is actually needed, it is
requested/captured from AI Streaming (the same published representation
Live Streaming already subscribes to), never a new output DeepStream
creates for this purpose — see `docs/DEEPSTREAM_PIPELINE_SPEC.md` Stage
8.7. AI Runtime gains no JPEG/image-writing responsibility.

Responsibilities:

- Full-frame snapshots
- Object/person crops
- Evidence storage
- Incident attachment

Output:

- SnapshotCreatedEvent

---

## services/recording (Phase 9+, POSTPONED per ADR-029)

Deferred until services/evidence (Phase 8) is complete. Design
unchanged — snapshots moved to services/evidence; this service retains
continuous recording and event clips only.

Responsibilities:

- Event clips
- Recording retention
- Storage management

---

# shared/

Reusable components.

## shared/events

Event schemas.

---

## shared/schemas

API schemas.

---

## shared/constants

Shared enums and constants.

---

## shared/utils

Reusable helpers.

---

# configs/

System configuration.

Examples:

- cameras.yaml
- threat_rules.yaml
- recording.yaml
- calibration.yaml

---

# models/

Model artifacts.

- yolo26m_weapon.pt
- vit_48k_binary.pth

---

# tests/

Unit tests
Integration tests
Benchmark tests

---

# deployments/

Deployment artifacts.

- Docker
- Jetson deployment scripts

---

# Ownership Rules

apps/deepstream owns:

- Inference
- Tracking
- Classification (raw model output)
- Metadata publication (ObservationEvent — observations only, never a
  decision)

services/threat_engine owns:

- Threat decisions

services/incident_service owns:

- Distance estimation invocation
- Threat evaluation invocation
- Incident lifecycle

services/alert_service owns (ADR-029):

- Alert eligibility, dedup, escalation, notification

services/hardware_action owns (ADR-029):

- Physical actuation (GPIO, siren, floodlight, PTZ)

services/evidence owns (ADR-029):

- Snapshots, object/person crops, evidence storage

apps/api owns:

- Persistence
- API access

apps/frontend owns:

- Visualization

---

# Repository Principles

- Clear ownership
- No circular dependencies
- Shared code only in shared/
- Business rules isolated from inference pipeline
- Every subsystem owns exactly one business capability; no
  independently-deployed subsystem calls another's internal logic
  directly — communication between them is only through the EventBus
  (ADR-029). A subsystem's own in-process use of a library it is the
  sole caller of (e.g. Incident Service calling
  services/threat_engine/services/calibration) is not a cross-subsystem
  call and remains permitted.
- The EventBus is transport only: publish/subscribe/deliver, never
  filtering, routing logic, business rules, severity-based retries,
  transformation, or enrichment (ADR-029).
- AI Runtime publishes observations, never decisions (ADR-029).