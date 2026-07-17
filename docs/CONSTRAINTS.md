# Radar Eye Constraints

## Operational Constraints

- Air-gapped deployment
- No cloud dependency
- Offline-first operation
- Local-only processing

---

## Hardware Constraints

### Compute

- 2 × NVIDIA Jetson AGX Orin 32GB

### Cameras

- 20 RTSP cameras
- 4MP
- 30 FPS
- H.264

---

## Architecture Constraints

### Mandatory

- DeepStream

### Mandatory

- TensorRT

### Mandatory

- GPU-first processing

### Mandatory

- Zero-copy architecture wherever technically possible

Preferred path:

RTSP
→ NVDEC
→ DeepStream
→ TensorRT
→ Analytics
→ Metadata

Avoid:

GPU → CPU → GPU

transfers.

---

## Security Constraints

- No internet required for operation
- Local authentication
- Future LDAP/AD integration
- RBAC required

---

## Retention Constraints

- 30-day retention requirement exists
- Storage implementation not yet decided

---

## Unknowns

### Storage

UNKNOWN

### Database

UNKNOWN

### Event Transport

UNKNOWN

### Alarm Hardware

UNKNOWN

### Multi-Node Design

UNKNOWN

### Frontend Video Transport

UNKNOWN

### Aggregation Strategy

UNKNOWN