# Radar Eye Container Candidates

This document defines logical runtime containers.

No technology choices are finalized.

---

## C-001

Container:

Video Ingestion

Responsibilities:

- RTSP management
- Stream lifecycle
- Health monitoring

Consumes:

- RTSP streams

Produces:

- Video frames

---

## C-002

Container:

Inference Engine

Responsibilities:

- AI execution
- Detection generation

Consumes:

- Video frames

Produces:

- Detections

---

## C-003

Container:

Threat Engine

Responsibilities:

- Threat classification
- Severity assignment

Consumes:

- Detections

Produces:

- Threats

---

## C-004

Container:

Alert Engine

Responsibilities:

- Alert lifecycle
- Notification generation

Consumes:

- Threats

Produces:

- Alerts

---

## C-005

Container:

Recording Service

Responsibilities:

- Video retention
- Recording retrieval

Consumes:

- Video streams

Produces:

- Recordings

---

## C-006

Container:

Alarm Service

Responsibilities:

- Alarm execution
- Alarm state tracking

Consumes:

- Alerts

Produces:

- Alarm actions

---

## C-007

Container:

Identity Service

Responsibilities:

- Authentication
- Authorization

Consumes:

- Login requests

Produces:

- Access decisions

---

## C-008

Container:

Audit Service

Responsibilities:

- Audit collection
- Audit retrieval

Consumes:

- User actions
- System actions

Produces:

- Audit records

---

## C-009

Container:

Operator Application

Responsibilities:

- Live monitoring
- Incident investigation
- Playback

Consumes:

- System data

Produces:

- User actions

---

## C-010

Container:

Administration Application

Responsibilities:

- User management
- Camera management
- Configuration

Consumes:

- Administrative actions

Produces:

- Configuration changes

---

## C-011

Container:

Monitoring Service

Responsibilities:

- Health visibility
- Resource visibility

Consumes:

- Runtime telemetry

Produces:

- Health information