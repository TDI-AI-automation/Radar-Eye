# Radar Eye

Military AI Surveillance Platform

---

# Mission

Radar Eye is an AI-powered military surveillance platform designed to detect, classify, track, assess, and manage potential threats from RTSP camera streams running on NVIDIA Jetson AGX Orin edge devices.

The platform operates in air-gapped military environments and provides real-time situational awareness, incident management, and threat assessment.

---

# Architecture Authority

The architecture defined in the repository is authoritative.

Architecture changes require:

1. Human approval
2. Architecture review
3. ADR update

No implementation may bypass architecture decisions.

---

# Source of Truth

Priority Order:

1. PROJECT_CONTEXT.md
2. CLAUDE.md
3. docs/*
4. TASKS.md

If documents conflict:

PROJECT_CONTEXT.md wins.

---

# Core Technology Decisions

Deployment Target:
- NVIDIA Jetson AGX Orin 32GB

Video Analytics:
- NVIDIA DeepStream 7.0

Inference Runtime:
- TensorRT

Backend:
- FastAPI

Database:
- PostgreSQL

Tracking:
- NvDCF

Communication:
- Internal Event Bus

Recording:
- H.265 Archive
- Continuous Recording
- Event Clip Extraction

---

# Mandatory Rules

The following are mandatory:

- DeepStream is mandatory
- TensorRT is mandatory
- PostgreSQL is mandatory
- FastAPI is mandatory
- Event-driven architecture is mandatory
- Repository architecture must be respected
- Threat engine rules must follow THREAT_ENGINE_SPEC.md
- Event contracts must follow EVENT_CONTRACTS.md

---

# Prohibited

The following are prohibited unless explicitly approved:

- SQLite
- MongoDB
- OpenCV production inference pipelines
- YOLO execution outside DeepStream production pipelines
- Direct commits to master
- Architecture modifications without ADR
- Hardcoded configuration
- Hardcoded thresholds
- Business logic inside API routes

---

# Development Rules

Every change must originate from TASKS.md.

Every task must include:

- Owner
- Description
- Acceptance Criteria
- Dependencies

No implementation may begin without a task.

Unknowns remain UNKNOWN until validated.

Assumptions must be documented.

---

# Code Quality Rules

All production code must:

- Be typed where practical
- Include logging
- Handle failures gracefully
- Follow repository architecture
- Be testable
- Avoid global state
- Avoid hidden dependencies

---

# Performance Principles

The system is designed for:

- 20 Cameras
- Real-time processing
- Edge deployment
- Air-gapped operation
- Offline-first operation

Performance optimizations must not violate architecture constraints.

---

# Security Principles

Military deployment assumptions:

- Air-gapped environment
- Local-only operation
- RBAC authorization
- Auditability required
- Incident history immutable

Security is prioritized over convenience.

---

# Human Authority

Human (Tanvir) is the final authority.

Human decisions override all AI-generated decisions.

No AI agent may modify project scope.