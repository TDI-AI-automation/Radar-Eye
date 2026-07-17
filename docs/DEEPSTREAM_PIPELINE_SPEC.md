# DeepStream Pipeline Specification

## Purpose

Define the end-to-end video processing pipeline.

---

## Pipeline Overview

RTSP Camera
    ↓
StreamMux
    ↓
YOLO Detector
    ↓
NvDCF Tracker
    ↓
Uniform Classification
    ↓
Distance Estimation
    ↓
Threat Engine
    ↓
Incident Generation
    ↓
Recording
    ↓
API/Event Bus
    ↓
Frontend

---

# Stage 1: Camera Ingestion

Input:
- RTSP H.264
- RTSP H.265

Output:
- Decoded GPU Frames

---

# Stage 2: StreamMux

Responsibilities:
- Batch frames
- Synchronize streams

Inputs:
- Multiple cameras

Outputs:
- Batched frames

---

# Stage 3: Weapon/Person Detection

Model:
- yolo26m_weapon.pt

Outputs:
- Bounding boxes
- Confidence
- Class

Classes:
- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

---

# Stage 4: Tracking

Tracker:
- NvDCF

Outputs:
- Persistent Track IDs

Requirements:
- Support 20+ simultaneous persons

---

# Stage 5: Uniform Classification

Model:
- vit_48k_binary.pth

Input:
- Person crop

Output:
- military
- civilian
- unknown

---

# Stage 6: Distance Estimation

Method:
- Ground Plane Projection

Inputs:
- Person foot point
- Calibration

Outputs:
- Estimated distance
- Zone

---

# Stage 7: Threat Engine

Inputs:
- Weapon
- Uniform
- Zone

Outputs:
- Threat level

---

# Stage 8: Incident Generation

Creates:
- Incident record
- Snapshot
- Clip request

---

# Stage 9: Recording

Continuous recording

Event clip extraction:
- Pre-event window
- Post-event window

---

# Stage 10: Event Publication

Publishes:
- Detection events
- Incident events
- System events

Consumers:
- Backend
- Frontend
- Alert services