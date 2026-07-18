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

---

# AI Development Workflow

## Repository Startup Procedure

Every new AI session starts with zero conversation memory.

Before planning or writing code, reconstruct project context by reading repository documentation, in this order:

1. CLAUDE.md
2. PROJECT_CONTEXT.md
3. ADR_INDEX.md
4. TASKS.md
5. IMPLEMENTATION_STATUS.md
6. Subsystem documentation and source code

Do not begin implementation before completing this sequence.

---

## Repository Authority Hierarchy

The repository is the project's permanent memory.

Conversation history is not authoritative and does not survive between sessions.

Authority order, highest first:

1. Architecture documentation (see Priority Order above)
2. PROJECT_CONTEXT.md
3. TASKS.md
4. IMPLEMENTATION_STATUS.md
5. Source code
6. Conversation context

If conflicts occur:

Higher authority wins.

Conversation context never overrides the repository.

---

## Standard Development Workflow

1. Read repository documentation.
2. Reconstruct project understanding.
3. Review assigned work.
4. Identify affected files.
5. Present implementation plan.
6. Wait for approval.
7. Implement only approved scope.
8. Run verification.
9. Update IMPLEMENTATION_STATUS.md if implementation state changed.
10. Summarize completed work.

---

## Implementation Rules

Never modify architecture without explicit approval.

Unknowns remain unknown until validated.

Avoid assumptions.

Keep changes narrowly scoped.

Do not perform unrelated refactoring.

Preserve repository conventions.

Minimize implementation blast radius.

---

## Multi-Agent Collaboration

Respect subsystem ownership.

Do not overwrite unrelated work.

Coordinate through repository documentation, not conversation memory.

TASKS.md is the authoritative execution plan.

IMPLEMENTATION_STATUS.md is the operational implementation state.

---

## Conflict Resolution

Architecture conflicts:

Stop implementation. Request clarification.

Task conflicts:

Request clarification.

Implementation status conflicts:

Verify against source code first.

Update IMPLEMENTATION_STATUS.md if necessary.

---

## Completion Procedure

Before considering work complete:

- Verify implementation.
- Update IMPLEMENTATION_STATUS.md if required.
- Ensure repository documentation remains consistent.
- Summarize completed work.