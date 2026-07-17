# Data Ownership Specification

## Purpose

Define which component owns which data.

Ownership means:

- Creates data
- Updates data
- Deletes data
- Defines schema

---

# Camera

Owner:

apps/api

Database Tables:

- cameras

Responsibilities:

- Camera registration
- Camera configuration
- Camera status

---

# Camera Calibration

Owner:

services/calibration

Database Tables:

- camera_calibrations

Responsibilities:

- Homography storage
- Calibration versioning
- Zone mapping

---

# Track Data

Owner:

apps/deepstream

Persistence:

None (ephemeral)

Responsibilities:

- Track creation
- Track update
- Track termination

Retention:

Memory only

---

# Detection Data

Owner:

apps/deepstream

Persistence:

None

Responsibilities:

- Object detections
- Confidence scores

Retention:

Frame lifetime only

---

# Uniform Classification

Owner:

apps/deepstream

Persistence:

None

Responsibilities:

- Military/Civilian classification

Retention:

Track lifetime

---

# Distance Estimation

Owner:

services/calibration

Persistence:

None

Responsibilities:

- Distance calculation
- Zone calculation

Retention:

Track lifetime

---

# Threat Assessment

Owner:

services/threat_engine

Persistence:

incident_events

Responsibilities:

- Threat evaluation
- Threat level generation

---

# Incident

Owner:

services/incident_service

Database Tables:

- incidents

Responsibilities:

- Create
- Update
- Resolve
- Archive

---

# Incident Events

Owner:

services/incident_service

Database Tables:

- incident_events

Responsibilities:

- State transitions
- Audit history

---

# Snapshots

Owner:

services/recording

Storage:

filesystem

Metadata Table:

- snapshots

---

# Event Clips

Owner:

services/recording

Storage:

filesystem

Metadata Table:

- recordings

---

# System Events

Owner:

apps/api

Database Tables:

- system_events

Responsibilities:

- Health events
- Error events
- Audit events

---

# Ownership Rules

Only the owner may:

- Change schema
- Delete data
- Modify records

Other services:

- Read through contracts
- Never modify directly

---

# Design Principle

Single Owner Per Data Entity