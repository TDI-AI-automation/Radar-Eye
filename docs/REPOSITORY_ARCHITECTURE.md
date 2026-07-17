# Repository Architecture

## Purpose

Define the physical repository layout and ownership boundaries.

---

# Top-Level Structure

radar-eye/

├── apps/
├── services/
├── shared/
├── configs/
├── models/
├── scripts/
├── tests/
├── deployments/
├── docs/

---

# apps/

Contains executable applications.

## apps/deepstream

Responsibilities:

- Camera ingestion
- DeepStream pipeline
- Detection
- Tracking
- Classification
- Distance estimation

Outputs:

- Threat assessment events
- Incident candidate events

---

## apps/api

Responsibilities:

- FastAPI backend
- REST APIs
- WebSocket APIs
- Authentication
- Database access

---

## apps/frontend

Responsibilities:

- Dashboard
- Incident management
- Playback
- Live monitoring

---

# services/

Contains business services.

## services/threat_engine

Responsibilities:

- Threat evaluation
- Threat scoring
- Threat rules

Input:

- Detection data
- Classification data
- Distance data

Output:

- Threat level

---

## services/incident_service

Responsibilities:

- Incident creation
- Incident updates
- Incident lifecycle management

---

## services/calibration

Responsibilities:

- Homography management
- Zone calculation
- Distance estimation support

---

## services/recording

Responsibilities:

- Event clips
- Recording retention
- Storage management

---

# shared/

Reusable components.

## shared/events

Event schemas.

---

## shared/schemas

API schemas.

---

## shared/constants

Shared enums and constants.

---

## shared/utils

Reusable helpers.

---

# configs/

System configuration.

Examples:

- cameras.yaml
- threat_rules.yaml
- recording.yaml
- calibration.yaml

---

# models/

Model artifacts.

- yolo26m_weapon.pt
- vit_48k_binary.pth

---

# tests/

Unit tests
Integration tests
Benchmark tests

---

# deployments/

Deployment artifacts.

- Docker
- Jetson deployment scripts

---

# Ownership Rules

apps/deepstream owns:

- Inference
- Tracking

services/threat_engine owns:

- Threat decisions

services/incident_service owns:

- Incident lifecycle

apps/api owns:

- Persistence
- API access

apps/frontend owns:

- Visualization

---

# Repository Principles

- Clear ownership
- No circular dependencies
- Shared code only in shared/
- Business rules isolated from inference pipeline