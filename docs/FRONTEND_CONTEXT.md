# Frontend Context

---

# Frontend Repository

Name:
radar-eye-command

URL:
https://github.com/CodeHub1443/radar-eye-command

Purpose:
Radar Eye Command Center User Interface

Status:
Prototype UI Complete

Integration Status:
Not Yet Integrated

Architecture Status:
Requires Alignment With Backend Architecture

---

# Technology Stack

Framework:
React 19

Language:
TypeScript

Build Tool:
Vite

Routing:
TanStack Router

Data Fetching:
TanStack Query

UI Framework:
TailwindCSS

Component Library:
Radix UI

Icons:
Lucide React

---

# Design Goal

Provide a real-time military command center interface for:

- Surveillance Operations
- Threat Monitoring
- Incident Management
- Tactical Visualization
- System Monitoring
- Evidence Review

---

# Current State

The frontend is primarily driven by mocked data.

Current implementation relies on:

src/lib/mock-data.ts

for:

- Cameras
- Alerts
- Incidents
- Analytics
- System Health

The UI architecture is mature but backend integration is incomplete.

---

# Integration Strategy

The frontend shall transition from:

Mock Data
    ->
REST APIs
    +
WebSocket Streams

All operational data shall originate from Radar Eye backend services.

---

# Major Architectural Alignment Required

Threat Model

Current:
- Alert Level 1
- Alert Level 2
- Alert Level 3

Required:
- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

---

# Health Monitoring Alignment

Current UI contains generic infrastructure metrics.

Required deployment model:

- NVIDIA Jetson AGX Orin 32GB
- DeepStream
- TensorRT
- PostgreSQL

All health metrics shall represent actual deployment hardware.

---

# Frontend Ownership

Owner:
@frontend

Architecture Authority:
@architect

Backend Integration Authority:
@backend

Changes affecting architecture require review.