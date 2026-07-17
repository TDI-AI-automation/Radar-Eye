# Radar Eye Architecture Decision Records

Purpose:

Track all architecture decisions.

No architecture decision is considered final unless documented in this file.

---

# ADR-001

Decision:

DeepStream as mandatory video processing framework.

Status:

ACCEPTED

Reason:

Production-grade GPU accelerated video analytics on NVIDIA Jetson.

---

# ADR-002

Decision:

TensorRT as mandatory production inference runtime.

Status:

ACCEPTED

Reason:

Required for real-time edge inference performance.

---

# ADR-003

Decision:

Offline-First Architecture.

Status:

ACCEPTED

Reason:

Military deployments cannot depend on internet connectivity.

---

# ADR-004

Decision:

Air-Gapped Deployment Support.

Status:

ACCEPTED

Reason:

Military deployment requirement.

---

# ADR-005

Decision:

Zero-Copy Processing Preferred.

Status:

ACCEPTED

Reason:

Reduce memory transfer overhead and maximize throughput.

---

# ADR-006

Decision:

PostgreSQL selected as primary database.

Status:

ACCEPTED

Reason:

Structured relational data, auditability, operational simplicity, offline deployment support.

---

# ADR-007

Decision:

Internal Event-Driven Architecture.

Status:

ACCEPTED

Reason:

Loose coupling between DeepStream, Threat Engine, Incident Service, Recording Service, API Service and future components.

---

# ADR-008

Decision:

Metadata-only storage architecture.

Status:

ACCEPTED

Reason:

Store incidents, evidence metadata, audit history and configuration.

Do not store frames, detections, tracks or per-frame analytics.

---

# ADR-009

Decision:

Authentication Architecture.

Status:

ACCEPTED

Initial State:

Local users.

Future State:

LDAP / Active Directory integration.

Reason:

Military deployments require local operation while preserving future enterprise integration.

---

# ADR-010

Decision:

Single Node Deployment Architecture.

Status:

ACCEPTED

Deployment:

1 × Jetson AGX Orin 32GB

Camera Capacity:

20 Cameras

Reason:

Simpler deployment and operations.

---

# ADR-011

Decision:

Frontend Video Delivery Strategy.

Status:

ACCEPTED

Strategy:

Backend-controlled video delivery.

Realtime metadata delivered via WebSocket.

Reason:

Centralized access control and simplified frontend integration.

---

# ADR-012

Decision:

Alarm Integration Protocol.

Status:

ACCEPTED

Supported Targets:

- Relay Controller
- GPIO Relay
- Siren
- Beacon Light

Trigger Source:

Threat Engine

Reason:

Hardware independence.

---

# ADR-013

Decision:

Tracker Selection.

Status:

ACCEPTED

Selected Tracker:

NvDCF

Reason:

DeepStream native integration and persistent tracking performance.

---

# ADR-014

Decision:

Primary Detector Selection.

Status:

ACCEPTED

Selected Detector:

YOLO26M Weapon Detector

Model:

models/yolo26m_weapon.pt

Reason:

Project benchmark selection.

---

# ADR-015

Decision:

Threat Engine Architecture.

Status:

ACCEPTED

Type:

Rule-Based Threat Evaluation Engine.

Inputs:

- Weapon Type
- Uniform Classification
- Distance Zone

Outputs:

- Threat Level
- Incident Decisions
- Alarm Decisions

Reason:

Deterministic and auditable behavior.

---

# ADR-016

Decision:

Distance Estimation Strategy.

Status:

ACCEPTED

Method:

Ground Plane Projection

Calibration:

- Installer Calibration
- Operator Recalibration

Reason:

Operational simplicity and explainability.

---

# ADR-017

Decision:

Recording Strategy.

Status:

ACCEPTED

Recording:

Continuous Recording

Evidence:

Event Clip Extraction

Codec:

H.265

Retention:

30 Days

Reason:

Operational investigation requirements.

---

# ADR-018

Decision:

Backend Framework.

Status:

ACCEPTED

Framework:

FastAPI

Reason:

High performance, type safety and API-first development.

---

# ADR-019

Decision:

Deployment Hardware.

Status:

ACCEPTED

Hardware:

NVIDIA Jetson AGX Orin 32GB

Reason:

Project deployment target.

---

# ADR-020

Decision:

Frontend Reuse Strategy.

Status:

ACCEPTED

Frontend Repository:

https://github.com/CodeHub1443/radar-eye-command

Strategy:

Reuse existing frontend.

Replace mock data with APIs and WebSocket streams.

Reason:

Reduce development time.

---

# ADR-021

Decision:

Threat Escalation Policy.

Status:

ACCEPTED

Rules:

HIGH:
- 3 consecutive frames -> ThreatAssessmentEvent
- 1 second sustained -> Incident
- 3 seconds sustained -> Alarm

MEDIUM:
- 2 seconds sustained -> Incident

LOW:
- Dashboard only

Fire:
- Immediate HIGH
- Immediate Incident
- Immediate Alarm

Reason:

Reduce false positives while maintaining operational responsiveness.

---

# ADR-022

Decision:

Threat De-escalation Policy.

Status:

ACCEPTED

Rules:

HIGH:
- Threat absent for 10 seconds

MEDIUM:
- Threat absent for 5 seconds

LOW:
- Threat absent for 3 seconds

Reason:

Prevent oscillation and alert fatigue.

---

# ADR-023

Decision:

Human Review Workflow.

Status:

ACCEPTED

Trigger:

Uniform Classification = Unknown

Action:

Create HUMAN_REVIEW item.

Operator Actions:

- Confirm Military
- Confirm Civilian
- Escalate
- Dismiss

Reason:

Prevent automatic decisions on uncertain classifications.

---

# ADR-024

Decision:

Incident Creation Policy.

Status:

ACCEPTED

HIGH:
- Incident Created

MEDIUM:
- Incident Created

LOW:
- No Incident

ALLY:
- No Incident

OBSERVE:
- No Incident

HUMAN_REVIEW:
- No Incident

Reason:

Reduce operational noise.

---

# ADR-025

Decision:

Incident Deduplication Policy.

Status:

ACCEPTED

Rule:

1 Track = 1 Active Incident

Incident Ends When:

- Track Lost > 10 Seconds
OR
- Operator Closes Incident

Reason:

Prevent duplicate incidents.

---

# ADR-026

Decision:

Alarm Trigger Policy.

Status:

ACCEPTED

HIGH:
- Alarm Eligible

MEDIUM:
- No Alarm

LOW:
- No Alarm

ALLY:
- No Alarm

OBSERVE:
- No Alarm

HUMAN_REVIEW:
- No Alarm

Fire:
- Immediate Alarm

Reason:

Prevent unnecessary alarm activations.