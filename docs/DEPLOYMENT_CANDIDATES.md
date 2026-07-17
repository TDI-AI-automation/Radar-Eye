# Radar Eye Deployment Candidates

Technology selections are intentionally deferred.

---

## Node-001

Name:

Jetson-A

Responsibilities:

- Cameras 1–10
- Video ingestion
- AI inference

Status:

ASSUMED

---

## Node-002

Name:

Jetson-B

Responsibilities:

- Cameras 11–20
- Video ingestion
- AI inference

Status:

ASSUMED

---

## Node-003

Name:

Operator Workstation

Responsibilities:

- Monitoring
- Alert handling
- Playback

Status:

EXPECTED

---

## Node-004

Name:

Administration Workstation

Responsibilities:

- User management
- Configuration
- Audit review

Status:

EXPECTED

---

## Node-005

Name:

Central Server

Responsibilities:

UNKNOWN

Status:

OPEN QUESTION

Reference:

Q-006

---

## Network Topology

RTSP Cameras

↓

Jetson Nodes

↓

Operator / Admin Interfaces

---

## Unknowns

- Central aggregation strategy
- Multi-node coordination strategy
- Metadata synchronization strategy
- Event transport strategy
- Storage placement strategy
- Alarm integration strategy