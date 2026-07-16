# Radar Eye Project Context
## PROJECT_CONTEXT.md file

## Mission

Military AI surveillance system for Bangladesh Army camps.

---

## Deployment Model

- Air-gapped
- Offline-first
- Local-only operation
- No cloud dependency

---

## Hardware

### Edge Nodes

- 2 × NVIDIA Jetson AGX Orin 32GB Dev Kit

### Cameras

- 20 cameras total
- Dahua / Hikvision
- 4MP
- 30 FPS
- H.264
- RTSP streams

### Distribution

Jetson A:
- Camera 1–10

Jetson B:
- Camera 11–20

---

## AI Stack

### Runtime

- DeepStream 7.0
- JetPack 6.2
- CUDA 12.2

### Models

Primary:
- YOLO

Secondary:
- ViT Classifier

### Detection Classes

- Person
- Rifle
- RPG
- Pistol
- Fire

### Classification

- Military
- Civilian

---

## Frontend

Repository:
https://github.com/CodeHub1443/radar-eye-command

Language:
- TypeScript

Authentication:
- Not implemented

---

## Security

Authentication:
- Local users

Future:
- LDAP / Active Directory

Authorization:
- RBAC

---

## Data Retention

- 30 days

---

## Alarm System

Status:
- Hardware not finalized

Candidates:
- Industrial relay controller
- GPIO relay board
- Siren
- Beacon light

---

## Future Analytics

- Tripwire
- Virtual Fence
- Loitering
- Crowd Density
- Abandoned Object
- Camera Blindness Detection
- Cross Camera Tracking
