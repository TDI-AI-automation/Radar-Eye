# CLAUDE.md

## Project

Radar Eye

AI-powered military surveillance and threat assessment platform.

Primary deployment target:

- Jetson AGX Orin 32GB
- DeepStream
- TensorRT
- FastAPI
- PostgreSQL

Current deployment:

- Single node
- Air-gapped
- 20 cameras

---

# Architecture Rules

All implementation must follow approved architecture documents.

Priority Order:

1. ADR_INDEX.md
2. THREAT_ENGINE_SPEC.md
3. EVENT_CONTRACTS.md
4. DATABASE_SCHEMA.md
5. DEEPSTREAM_PIPELINE_SPEC.md
6. FRONTEND_BACKEND_CONTRACTS.md
7. AGENTS.md

If conflicts occur:

Higher priority document wins.

---

# Core Principles

## Deterministic Decisions

Threat evaluation must be rule-based.

No LLM may make threat decisions.

---

## Event Driven Design

Preferred:

Producer -> Event -> Consumer

Avoid:

Direct service coupling.

---

## Offline First

System must operate without internet access.

Internet connectivity is optional.

---

## Evidence Preservation

Every HIGH threat incident must retain:

- Snapshot
- Event clip
- Incident timeline

---

## Auditability

All threat decisions must be explainable.

Every incident must have:

- Detection source
- Classification result
- Distance zone
- Threat level

---

# AI Components

## Detection

Model:

YOLO26M

Purpose:

Weapon detection

---

## Tracking

Tracker:

NvDCF

Purpose:

Persistent tracking

---

## Classification

Model:

ViT Binary Classifier

Outputs:

- military
- civilian
- unknown

---

## Distance Estimation

Method:

Ground Plane Projection

Outputs:

- zone_1
- zone_2
- zone_3

---

## Threat Engine

Inputs:

- weapon type
- classification
- distance zone

Outputs:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH
- HUMAN_REVIEW

---

# Backend Constraints

Framework:

FastAPI

Database:

PostgreSQL

Communication:

REST + WebSocket

Avoid:

GraphQL

Avoid:

Tightly coupled services

---

# Frontend Constraints

Frontend repository:

radar-eye-command

Use:

REST APIs

Use:

WebSocket events

Avoid:

Mock data

Avoid:

Polling where practical

---

# Recording Rules

Continuous recording enabled.

Store:

H.265 archive

Retention:

30 days

Generate:

- snapshots
- event clips

---

# Human Review Rules

Unknown uniforms must never be auto-resolved.

Create review item.

Operator action required.

Allowed actions:

- Confirm Military
- Confirm Civilian
- Escalate
- Dismiss

---

# Alarm Rules

HIGH:

Alarm eligible

MEDIUM:

No alarm

LOW:

No alarm

ALLY:

No alarm

OBSERVE:

No alarm

FIRE:

Immediate alarm

---

# Scalability

Current:

Single Jetson

Future:

- Multi-node
- Distributed event bus
- Distributed storage

Do not introduce design decisions that block future scaling.