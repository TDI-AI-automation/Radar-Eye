# DeepStream Pipeline Specification

## Purpose

Define the end-to-end real-time video analytics pipeline.

This document is the authoritative specification for all DeepStream processing stages.

---

# Pipeline Overview

RTSP Camera
    ↓
Source Bin
    ↓
StreamMux
    ↓
Primary GIE (Detector)
    ↓
NvDCF Tracker
    ↓
Secondary GIE (Uniform Classifier)
    ↓
Distance Estimation
    ↓
Threat Engine
    ↓
Incident Service
    ↓
Recording Service
    ↓
Event Bus
    ↓
API Service
    ↓
Frontend

---

# Stage 1: Camera Ingestion

Input:

- RTSP H.264

Camera Count:

- 20 Cameras

Deployment Target:

- 1 × Jetson AGX Orin 32GB

Output:

- GPU Decoded Frames

Requirements:

- Reconnect automatically
- Detect camera failures
- Emit CameraDisconnectedEvent

---

# Stage 2: StreamMux

Component:

nvstreammux

Responsibilities:

- Stream synchronization
- Batch generation
- Frame aggregation

Input:

- Multiple camera streams

Output:

- Batched GPU frames

---

# Stage 3: Primary GIE

Purpose:

Weapon and person detection.

Model:

models/yolo26m_weapon.pt

Runtime:

TensorRT

Outputs:

- Bounding Boxes
- Confidence
- Class IDs

Supported Classes:

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

Output Metadata:

{
  "camera_id": "...",
  "class_id": "...",
  "confidence": 0.95,
  "bbox": {}
}

---

# Stage 4: Tracking

Component:

NvDCF

Purpose:

Persistent object tracking.

Outputs:

- Track IDs

Requirements:

- Support 20+ simultaneous persons
- Stable track persistence
- Re-identification support where available

Output Metadata:

{
  "track_id": 123
}

---

# Stage 5: Secondary GIE

Purpose:

Uniform Classification.

Model:

models/vit_48k_binary.pth

Runtime:

TensorRT

Input:

Person crop from tracker output.

Output Classes:

- military
- civilian
- unknown

Output Metadata:

{
  "track_id": 123,
  "uniform": "civilian"
}

---

# Stage 6: Distance Estimation

Purpose:

Estimate distance from camera.

Method:

Ground Plane Projection

Inputs:

- Track Position
- Camera Calibration

Outputs:

- Distance
- Zone

Zones:

zone_1
0m - 20m

zone_2
20m - 50m

zone_3
50m+

Output Metadata:

{
  "track_id": 123,
  "distance": 12.5,
  "zone": "zone_1"
}

---

# Stage 7: Threat Engine

Purpose:

Threat Classification.

Inputs:

- Weapon Type
- Uniform Class
- Distance Zone

Outputs:

- Threat Level
- Human Review Decision
- Incident Decision
- Alarm Decision

Threat Levels:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH
- HUMAN_REVIEW

Generated Events:

- ThreatAssessmentEvent
- HumanReviewItemCreatedEvent
- AlarmRequestedEvent

---

# Stage 8: Incident Service

Purpose:

Incident lifecycle management.

Responsibilities:

- Incident creation
- Incident updates
- Deduplication

Rule:

1 Track = 1 Active Incident

Outputs:

- IncidentCreatedEvent
- IncidentUpdatedEvent

---

# Stage 9: Recording Service

Purpose:

Evidence generation.

Recording Mode:

Continuous Recording

Codec:

H.265

Retention:

30 Days

Evidence Types:

- Snapshots
- Event Clips

Clip Policy:

Pre-event buffer
+
Post-event buffer

Generated Events:

- SnapshotCreatedEvent
- ClipCreatedEvent

---

# Stage 10: Event Bus

Purpose:

Internal service communication.

Consumers:

- API Service
- Recording Service
- Incident Service
- Alarm Service

Transport:

Internal Event Bus

Requirements:

- Immutable events
- Versioned contracts

---

# Stage 11: API Service

Purpose:

Expose system functionality.

Interfaces:

- REST API
- WebSocket API

Responsibilities:

- Frontend integration
- Incident retrieval
- Threat retrieval
- Evidence retrieval

---

# Stage 12: Frontend

Repository:

https://github.com/CodeHub1443/radar-eye-command

Consumes:

- REST APIs
- WebSocket Events

Provides:

- Live Monitoring
- Incident Center
- Tactical Map
- Threat Review Center
- Calibration Center
- Evidence Viewer

---

# Failure Handling

## Camera Failure

Generate:

CameraDisconnectedEvent

---

## Model Failure

Generate:

SystemEvent

Severity:

ERROR

---

## Calibration Failure

Generate:

SystemEvent

Severity:

ERROR

---

## Event Bus Failure

Generate:

SystemEvent

Severity:

CRITICAL

---

# Performance Targets

Camera Count:

20

Processing:

Real-Time

Deployment:

Jetson AGX Orin 32GB

Architecture:

Air-Gapped
Offline-First

---

# Architecture Constraints

Mandatory:

- DeepStream
- TensorRT
- NvDCF
- PostgreSQL
- FastAPI

Prohibited:

- OpenCV Production Pipelines
- SQLite
- MongoDB
- Direct YOLO Execution Outside DeepStream