# Radar Eye Data Ownership

## D-001

Data:

Camera Configuration

Owner:

Administration Application

Consumers:

- Video Ingestion

---

## D-002

Data:

Video Frames

Owner:

Video Ingestion

Consumers:

- Inference Engine

---

## D-003

Data:

Detections

Owner:

Inference Engine

Consumers:

- Threat Engine

---

## D-004

Data:

Threats

Owner:

Threat Engine

Consumers:

- Alert Engine
- Alarm Service

---

## D-005

Data:

Alerts

Owner:

Alert Engine

Consumers:

- Operator Application
- Alarm Service

---

## D-006

Data:

Recordings

Owner:

Recording Service

Consumers:

- Operator Application

---

## D-007

Data:

Users

Owner:

Identity Service

Consumers:

- Administration Application

---

## D-008

Data:

Roles

Owner:

Identity Service

Consumers:

- Administration Application

---

## D-009

Data:

Audit Records

Owner:

Audit Service

Consumers:

- Administration Application

---

## D-010

Data:

Health Metrics

Owner:

Monitoring Service

Consumers:

- Operator Application
- Administration Application

---

## D-011

Data:

Alarm State

Owner:

Alarm Service

Consumers:

- Operator Application

---

## Rule

Every data object shall have exactly one authoritative owner.