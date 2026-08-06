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
4. TASKS.md (root) — ticket-level backlog
5. docs/IMPLEMENTATION_ROADMAP.md — milestone sequencing (the single source of truth for what "RM-XX" means)
6. docs/IMPLEMENTATION_STATUS.md — current build state and subsystem branch assignments
7. Subsystem documentation and source code

Do not begin implementation before completing this sequence.

---

## Repository Authority Hierarchy

The repository is the project's permanent memory.

Conversation history is not authoritative and does not survive between sessions.

Authority order, highest first:

1. Architecture documentation (see Priority Order above)
2. PROJECT_CONTEXT.md
3. TASKS.md (root) — ticket-level backlog
4. docs/IMPLEMENTATION_ROADMAP.md — milestone sequence (authoritative for RM-XX definitions)
5. docs/IMPLEMENTATION_STATUS.md — current build state
6. Source code
7. Conversation context

If conflicts occur:

Higher authority wins.

Conversation context never overrides the repository.

---

## Standard Development Workflow

1. Read repository documentation.
2. Reconstruct project understanding.
3. Review assigned work.
4. Identify affected files.
5. Identify the owning subsystem branch (see "Git Branching & Merge Strategy" below); branch a short-lived ticket branch from it if the work is large enough to warrant one.
6. Present implementation plan.
7. Wait for approval.
8. Implement only approved scope.
9. Run verification.
10. Commit and push to the subsystem (or ticket) branch.
11. Update IMPLEMENTATION_STATUS.md if implementation state changed.
12. Summarize completed work.

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

TASKS.md (root) is the authoritative ticket-level execution plan.

docs/IMPLEMENTATION_ROADMAP.md is the authoritative milestone sequence — what each RM-XX covers and in what order.

IMPLEMENTATION_STATUS.md is the operational implementation state — what is built, and on which subsystem branch.

Milestones are a planning concept only. They are never Git branch names — see "Git Branching & Merge Strategy" below.

---

## Git Branching & Merge Strategy

Four distinct concerns, kept separate:

**Implementation order** — governed by docs/IMPLEMENTATION_ROADMAP.md. Milestones (RM-XX) sequence work; they are not Git branches.

**Subsystem ownership** — each subsystem branch owns one logical part of the architecture. See docs/IMPLEMENTATION_STATUS.md's Subsystem Status table for the current list and their corresponding apps/, services/, or shared/ paths.

**Git branching** — branch hierarchy, top to bottom:

```
main (production)
    ↑
develop (integration)
    ↑
long-lived subsystem branches
    ↑
optional short-lived ticket branches
```

- `main` — production only. Never developed on directly. Only receives merges from `develop`, and only at a full production release (see Production Release Gate below).
- `develop` — the primary integration branch. Every completed, reviewed subsystem milestone merges here. Continuous integration and integration testing run against `develop`. It always represents the latest integrated engineering build.
- Long-lived subsystem branches (feature/api, feature/deepstream, feature/threat-engine, feature/incident-service, feature/recording, feature/calibration, feature/shared-contracts, feature/frontend-integration, feature/developer-infrastructure, feature/testing) each own one logical part of the architecture. A milestone is implemented on the subsystem branch its work belongs to. New subsystems introduced by the Media Architecture Reset (ADR-028, ADR-029) — apps/ingestion, apps/live_stream, services/alert_service, services/hardware_action, services/evidence — are developed on `feature/media-architecture-reset` pending their own promotion to long-lived subsystem branches; see PROJECT_CONTEXT.md's Repository section.
- If a milestone is large enough to need parallel work, short-lived ticket branches branch from the subsystem branch (e.g. feature/RE-301-rtsp-ingestion from feature/deepstream) and merge back into it after review.

**Merge strategy** — Developer → ticket branch (optional) → subsystem branch → Principal Engineer review → testing → merge into `develop` (regular merge commit, never squash) → integration testing on `develop`. `develop` never receives a direct commit outside of these subsystem merges. Repeat across all subsystems until end-to-end validation and a production readiness review are complete, then merge `develop` → `main` for a production release.

**Production Release Gate** — `develop` must not be merged into `main` until ALL of the following are complete: every roadmap milestone implemented; DeepStream pipeline, AI pipeline, API, frontend, database, event bus, incident pipeline, recording, alarm pipeline, and calibration all integrated; Developer Infrastructure and Testing subsystems complete; end-to-end integration tests passing; system acceptance testing complete; architecture review passed; production deployment validated. Only then may `develop` be merged into `main`.

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