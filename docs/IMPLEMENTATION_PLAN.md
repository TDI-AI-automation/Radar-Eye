# Implementation Plan

## Phase 1 - Foundation

- Repository skeleton
- Python package structure
- Config system
- Logging
- PostgreSQL setup
- Alembic migrations

Deliverable:
System boots successfully

---

## Phase 2 - Shared Contracts

- Event models
- Database models
- API schemas
- Constants

Deliverable:
Shared package complete

---

## Phase 3 - DeepStream Application

- Camera ingestion
- YOLO integration
- NvDCF integration
- ViT integration
- Distance estimation

Deliverable:
ThreatAssessmentEvent generated

---

## Phase 4 - Incident Service

- Incident creation
- Incident lifecycle
- Database persistence

Deliverable:
Incidents stored

---

## Phase 5 - Recording Service

- Snapshot extraction
- Event clips
- Retention management

Deliverable:
Evidence generated

---

## Phase 6 - API Service

- FastAPI
- REST endpoints
- WebSocket endpoints

Deliverable:
Frontend can consume data

---

## Phase 7 - Frontend Integration

- Dashboard
- Incident view
- Playback

Deliverable:
End-to-end workflow

---

## Phase 8 - Benchmark Validation

- Detector benchmarks
- Tracker benchmarks
- End-to-end latency
- Reliability tests

Deliverable:
Acceptance criteria validated