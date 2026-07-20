# Radar Eye Project Context

---

# Project

Name:
Radar Eye

Type:
Military AI Surveillance Platform

Status:
Architecture Complete
Implementation Phase Starting

---

# Mission

Provide real-time military surveillance, threat detection, threat assessment, incident management, and evidence generation using AI-powered video analytics.

---

# Documentation Map

CLAUDE.md:

Repository operating manual and AI development workflow.

PROJECT_CONTEXT.md:

Long-lived, mostly static project facts — vision, hardware, technology stack, repositories, deployment targets. This document.

TASKS.md:

Ticket-level execution plan, backlog, priorities, and active work. Format under review — not being changed at this time.

docs/IMPLEMENTATION_ROADMAP.md:

Authoritative implementation milestone sequence (RM-XX). Single source of truth for what each milestone covers and in what order.

IMPLEMENTATION_STATUS.md:

Operational implementation state — subsystem progress, current branch per subsystem, blockers, current implementation maturity.

Scope boundary:

This document holds stable facts, not implementation progress or Git branching mechanics.

For current progress or what to work on next, see docs/IMPLEMENTATION_ROADMAP.md and IMPLEMENTATION_STATUS.md. For branching and merge mechanics, see "# Repository" below and CLAUDE.md's "Git Branching & Merge Strategy" section.

---

# Deployment Model

Deployment Type:
Air-Gapped

Operation Mode:
Offline First

Network Dependency:
None

Cloud Dependency:
None

Primary Deployment:
Military Camps

---

# Hardware

Edge Compute:

- NVIDIA Jetson AGX Orin 32GB

Camera Count:

- 20 Cameras

Camera Type:

- Dahua
- Hikvision

Resolution:

- 4MP

Frame Rate:

- 30 FPS

Codec:

- H.264

Transport:

- RTSP

---

# AI Stack

Video Analytics:

- DeepStream 7.0

Inference Runtime:

- TensorRT

Object Detector:

- YOLO26M Weapon Detector

File:

models/yolo26m_weapon.pt

Tracker:

- NvDCF

Classifier:

- ViT Binary Classifier

File:

models/vit_48k_binary.pth

---

# Threat Classes

Threat Levels:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

---

# Classification Logic

Military + Weapon
    -> ALLY

Civilian + No Weapon
    -> OBSERVE

Civilian + Non-Lethal Weapon
    -> LOW

Civilian + Threat Weapon
    -> Distance Evaluation

Fire Detection
    -> HIGH

---

# Distance Zones

Zone 1:
0m - 20m

Zone 2:
20m - 50m

Zone 3:
50m+

---

# Distance Estimation

Method:

Ground Plane Projection

Calibration:

Installer Calibration
+
Operator Recalibration

---

# Backend

Framework:

FastAPI

Architecture:

Event Driven

---

# Database

Primary Database:

PostgreSQL

Stores:

- Incidents
- Audit Logs
- Threat Metadata
- Configuration
- Evidence Metadata

Does Not Store:

- Raw Frames
- Detection History
- Tracking History

---

# Recording

Policy:

Continuous Recording

Codec:

H.265

Retention:

30 Days

Additional:

Event Clip Extraction

---

# Repository

Branch Hierarchy:

```
main (production)
    ↑
develop (integration)
    ↑
long-lived subsystem branches
    ↑
optional short-lived ticket branches
```

- `main` — production only. Never developed on directly. Only receives merges from `develop`, and only once the full Production Release Gate (see CLAUDE.md's Git Branching & Merge Strategy) is satisfied.
- `develop` — the primary integration branch. Every completed, reviewed subsystem milestone merges here. Continuous integration runs against `develop`; it always reflects the latest integrated engineering build.
- Direct commits to `main` or `develop` are prohibited outside of reviewed subsystem-branch merges.

Branching Model:

Long-lived subsystem branches are the primary integration branches, each owning one logical part of the architecture:

- feature/api — apps/api (FastAPI service: persistence, event bus, auth/audit, lightweight health monitoring)
- feature/deepstream — apps/deepstream
- feature/threat-engine — services/threat_engine
- feature/incident-service — services/incident_service (also owns the Alarm Service until it warrants its own subsystem)
- feature/recording — services/recording
- feature/calibration — services/calibration
- feature/shared-contracts — shared/
- feature/frontend-integration — radar-eye-command integration
- feature/deployment — deployments/, scripts/
- feature/developer-infrastructure — formatting, linting, static analysis, dependency management, pre-commit, CI/CD, coverage tooling, developer workflow
- feature/testing — validation, regression testing, benchmarking, soak testing, and evaluation, ongoing throughout the project

Short-lived ticket branches may branch from a subsystem branch for large or parallelizable work, and merge back into it.

Subsystem branches merge into `develop` at a reviewed, approved integration point — not automatically after every milestone. `develop` merges into `main` only at a full production release.

Milestones (RM-XX, see docs/IMPLEMENTATION_ROADMAP.md) describe implementation sequencing only. They are not Git branch names.

---

# Repositories

## Backend Repository

Name:
Radar-Eye

URL:
https://github.com/TDI-AI-automation/Radar-Eye

Purpose:
Core surveillance platform.

---

## Frontend Repository

Name:
radar-eye-command

URL:
https://github.com/CodeHub1443/radar-eye-command

Purpose:
Radar Eye Command Center UI.

Technology:

- React 19
- TypeScript
- Vite
- TanStack Router
- TanStack Query
- TailwindCSS
- Radix UI

Status:
Prototype UI Complete

Integration Status:
Not Integrated

Notes:
Frontend was developed before architecture freeze.
Requires audit and API alignment.