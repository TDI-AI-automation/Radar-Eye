# Frontend Gap Analysis

---

# Audit Summary

Frontend Repository:
radar-eye-command

Assessment:

The frontend is substantially reusable.

Estimated Reuse:

70% - 80%

A complete rewrite is not required.

---

# Existing Strengths

The following areas align well with architecture:

- Live Monitoring
- Incident Center
- Tactical Map
- Camera Management
- Settings

These screens should be preserved and integrated.

---

# Mock Data Dependency

Current frontend relies heavily on:

src/lib/mock-data.ts

Contains:

- Cameras
- Alerts
- Incidents
- Analytics
- Health Metrics

This dependency must be removed.

Replacement Strategy:

React Query
+
Backend APIs
+
WebSocket Streams

---

# Threat Model Mismatch

Current UI:

- Alert Level 1
- Alert Level 2
- Alert Level 3

Architecture:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

Required Action:

Threat presentation layer redesign.

Priority:
High

---

# System Health Mismatch

Current UI references generic infrastructure.

Architecture requires:

- Jetson AGX Orin
- DeepStream
- TensorRT
- PostgreSQL

Required Action:

Deployment-specific health dashboards.

Priority:
Medium

---

# Missing Capability

Threat Review Center

Required By:

THREAT_ENGINE_SPEC.md

Status:

Missing

Priority:
High

---

# Missing Capability

Calibration Center

Required By:

CAMERA_CALIBRATION_SPEC.md

Status:

Missing

Priority:
High

---

# Missing Capability

Evidence Viewer

Required By:

RECORDING_POLICY.md

Status:

Missing

Priority:
Medium

---

# Integration Readiness

Frontend Structure:
Ready

Frontend Routing:
Ready

Frontend Component System:
Ready

Backend Integration:
Not Ready

Real-Time Event Integration:
Not Ready

Overall Assessment:

Frontend architecture is suitable for production evolution after backend integration.