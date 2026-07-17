# Radar Eye Agents

## Purpose

Define all autonomous software agents inside the Radar Eye platform.

Agents communicate through approved events and database state.

No agent may directly manipulate another agent's internal state.

---

# Agent 1: Video Ingestion Agent

## Responsibilities

- RTSP connection management
- Stream health monitoring
- Frame delivery to DeepStream

## Inputs

- Camera configuration

## Outputs

- Video frames
- CameraDisconnectedEvent

---

# Agent 2: Detection Agent

## Responsibilities

- Weapon detection

## Model

YOLO26M

## Outputs

- Bounding boxes
- Confidence scores

---

# Agent 3: Tracking Agent

## Responsibilities

- Persistent object tracking

## Tracker

NvDCF

## Outputs

- Stable track IDs

---

# Agent 4: Classification Agent

## Responsibilities

- Uniform classification

## Outputs

- military
- civilian
- unknown

---

# Agent 5: Distance Estimation Agent

## Responsibilities

- Ground plane projection
- Threat distance estimation

## Outputs

- zone_1
- zone_2
- zone_3

---

# Agent 6: Threat Assessment Agent

## Responsibilities

- Threat evaluation
- Rule execution
- Escalation handling
- De-escalation handling

## Outputs

- ThreatAssessmentEvent
- AlarmRequestedEvent
- HumanReviewItemCreatedEvent

---

# Agent 7: Incident Management Agent

## Responsibilities

- Incident creation
- Incident updates
- Deduplication

## Outputs

- IncidentCreatedEvent
- IncidentUpdatedEvent

---

# Agent 8: Evidence Agent

## Responsibilities

- Snapshot generation
- Event clip generation

## Outputs

- SnapshotCreatedEvent
- ClipCreatedEvent

---

# Agent 9: Recording Agent

## Responsibilities

- Continuous recording
- Archive management

## Outputs

- Recording metadata

---

# Agent 10: Human Review Agent

## Responsibilities

- Review queue creation
- Review status tracking

## Outputs

- Human review records

---

# Agent 11: Notification Agent

## Responsibilities

- Alarm routing
- Frontend notifications

## Outputs

- WebSocket notifications

---

# Agent 12: System Health Agent

## Responsibilities

- GPU monitoring
- Storage monitoring
- Service monitoring
- Camera monitoring

## Outputs

- SystemEvent
- CameraDisconnectedEvent

---

# Agent Communication Rules

Allowed:

Agent -> Event Bus -> Agent

Agent -> Database

Agent -> WebSocket Gateway

Not Allowed:

Agent -> Agent direct calls

Reason:

Loose coupling and future scalability.

---

# Deployment Scope

Current Deployment

- Single Jetson AGX Orin
- Single node
- 20 cameras

Future

- Multi-node
- Distributed event bus
- Distributed storage

Current implementation must remain compatible with future expansion.