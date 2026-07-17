# Radar Eye Requirements

## Mission

Provide real-time AI-assisted surveillance and threat detection for Army camps using CCTV infrastructure.

---

## Deployment Model

- Air-gapped
- Offline-first
- Local-only operation

---

## Hardware

### Edge Compute

- 2 × NVIDIA Jetson AGX Orin 32GB

### Cameras

- 20 cameras
- Dahua / Hikvision
- 4MP
- 30 FPS
- H.264
- RTSP

### Distribution

Jetson A
- Camera 1–10

Jetson B
- Camera 11–20

---

## AI Requirements

### Detection

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

- TypeScript frontend
- Existing repository available

---

## Security

Current:
- Local users

Future:
- LDAP
- Active Directory

Required:
- RBAC

---

## Data Retention

- 30 days

---

## Non-Functional Requirements

### Performance

- Real-time detection
- Multi-camera processing
- GPU-accelerated inference

### Reliability

- Continuous operation
- Automatic recovery from camera disconnects

### Security

- No cloud dependency
- Local processing only

---

## Architecture Constraints

### Mandatory

- DeepStream

### Mandatory

- TensorRT

### Mandatory

- Zero-copy architecture wherever technically possible

Preferred processing path:

RTSP
→ NVDEC
→ DeepStream
→ TensorRT
→ Analytics
→ Metadata

Avoid unnecessary:

GPU → CPU → GPU

transfers.

---

## Unknowns

- Storage architecture
- Database architecture
- Retention implementation
- Alarm hardware
- Event transport
- Multi-node topology
- Authentication implementation