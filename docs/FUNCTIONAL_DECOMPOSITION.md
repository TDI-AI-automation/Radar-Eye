# Radar Eye Functional Decomposition

## F-001 Video Ingestion

Responsibilities:

- RTSP connection management
- Stream health monitoring
- Decode pipeline entry

Inputs:

- RTSP streams

Outputs:

- Decoded frames

---

## F-002 AI Inference

Responsibilities:

- Object detection
- Classification
- Model execution

Inputs:

- Decoded frames

Outputs:

- Detections

---

## F-003 Threat Assessment

Responsibilities:

- Threat classification
- Severity assignment
- Threat generation

Inputs:

- Detections

Outputs:

- Threats

---

## F-004 Alert Management

Responsibilities:

- Alert creation
- Alert lifecycle
- Operator notification

Inputs:

- Threats

Outputs:

- Alerts

---

## F-005 Recording Management

Responsibilities:

- Video retention
- Recording indexing
- Playback support

Inputs:

- Video streams

Outputs:

- Recordings

---

## F-006 User Management

Responsibilities:

- User administration
- Role assignment
- Access control

Inputs:

- Administrative commands

Outputs:

- User updates

---

## F-007 Audit Management

Responsibilities:

- Audit capture
- Audit retrieval
- Audit storage

Inputs:

- User actions
- System actions

Outputs:

- Audit records

---

## F-008 Alarm Management

Responsibilities:

- Alarm execution
- Alarm state tracking

Inputs:

- Alerts

Outputs:

- Alarm commands

---

## F-009 Monitoring & Health

Responsibilities:

- System health visibility
- Service monitoring
- Resource monitoring

Inputs:

- Runtime telemetry

Outputs:

- Health status

---

## F-010 Operator Interface

Responsibilities:

- Live monitoring
- Alert investigation
- Event search
- Playback

Inputs:

- User actions

Outputs:

- Visualized information