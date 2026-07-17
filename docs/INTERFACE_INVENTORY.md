# Radar Eye Interface Inventory

## I-001

Interface:

RTSP Video Input

Provider:

Cameras

Consumer:

Video Ingestion

Status:

KNOWN

---

## I-002

Interface:

Frame Transfer

Provider:

Video Ingestion

Consumer:

Inference Engine

Status:

KNOWN

---

## I-003

Interface:

Detection Transfer

Provider:

Inference Engine

Consumer:

Threat Engine

Status:

KNOWN

---

## I-004

Interface:

Threat Transfer

Provider:

Threat Engine

Consumer:

Alert Engine

Status:

KNOWN

---

## I-005

Interface:

Alert Delivery

Provider:

Alert Engine

Consumer:

Operator Application

Status:

KNOWN

---

## I-006

Interface:

Alarm Command

Provider:

Alarm Service

Consumer:

Alarm Hardware

Status:

UNKNOWN

Reference:

Q-005

---

## I-007

Interface:

Authentication Request

Provider:

Operator Application

Consumer:

Identity Service

Status:

KNOWN

---

## I-008

Interface:

Authorization Request

Provider:

Applications

Consumer:

Identity Service

Status:

KNOWN

---

## I-009

Interface:

Audit Submission

Provider:

System Components

Consumer:

Audit Service

Status:

KNOWN

---

## I-010

Interface:

Health Reporting

Provider:

Runtime Components

Consumer:

Monitoring Service

Status:

KNOWN

---

## I-011

Interface:

Recording Retrieval

Provider:

Recording Service

Consumer:

Operator Application

Status:

KNOWN

---

## I-012

Interface:

Configuration Management

Provider:

Administration Application

Consumer:

Runtime Components

Status:

KNOWN

---

## Rule

Every interface must have:

- Provider
- Consumer
- Data Contract
- Failure Behavior

Technology remains undecided.