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

Primary Branch:

master

Implementation Branches:

feature/*

Direct commits to master are prohibited.

---

# Current Phase

Phase:
Implementation Phase 1

Current Goal:

Backend Foundation

Reference:

docs/IMPLEMENTATION_PLAN.md

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