# Radar Eye Technology Selection

## Status

IN PROGRESS

Technology selection is based on current architectural decisions and known deployment constraints.

Final acceptance requires benchmark validation.

---

## Hardware Platform

### Primary Inference Hardware

NVIDIA Jetson AGX Orin 32GB

Quantity:

- 2

Responsibilities:

- Video ingestion
- AI inference
- Object tracking
- Threat assessment
- Event generation
- Alert generation
- Recording management

Reason:

- CUDA acceleration
- TensorRT support
- DeepStream support
- Production-grade edge deployment
- Local operation without cloud dependency

---

## Video Ingestion

### Selected Technology

DeepStream

Components:

- nvurisrcbin
- nvstreammux
- nvvideoconvert
- nvdsosd

Reason:

- Native NVIDIA support
- Multi-stream optimization
- Zero-copy architecture
- Production-proven performance
- Jetson optimized

Status:

SELECTED

---

## Video Transport

### Selected Protocol

RTSP

Supported Codecs:

- H.264
- H.265

Reason:

- Industry standard
- Supported by deployed cameras
- Native DeepStream integration

Status:

SELECTED

---

## Object Detection

### Selected Model

yolo26m_weapon.pt

Framework:

- YOLO
- TensorRT optimized deployment

Output Classes:

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

Reason:

Current model aligns with operational threat classification requirements.

Status:

SELECTED

Validation Required:

- Accuracy benchmark
- Throughput benchmark
- TensorRT benchmark

---

## Uniform Classification

### Selected Model

vit_48k_binary.pth

Framework:

- Vision Transformer
- TensorRT optimized deployment

Output Classes:

- Military
- Civilian
- Unknown

Military Definition:

- Green camouflage torso
- Green camouflage pants
- Black boots

Unknown Definition:

- Confidence below configured threshold

Reason:

Matches operational requirements.

Status:

SELECTED

Validation Required:

- Accuracy benchmark
- TensorRT benchmark

---

## Object Tracking

### Selected Tracker

NvDCF

Framework:

- DeepStream NvMultiObjectTracker

Reason:

- Native DeepStream integration
- NVIDIA-supported
- Stable identity preservation
- Good occlusion handling
- Optimized for Jetson deployment
- Minimal custom implementation

Requirement:

Support at least:

- 20 simultaneous tracked persons per camera

Status:

SELECTED

Validation Required:

- ID switch benchmark
- Occlusion benchmark
- Throughput benchmark

---

## Distance Estimation

### Selected Method

Ground Plane Projection

Calibration Method:

Manual Ground Plane Calibration

Recalibration Method:

Operator Calibration Wizard

Inputs:

- Camera height
- Camera tilt angle
- Ground reference points

Output:

- Distance in meters
- Zone assignment

Zones:

- Zone 1 = 0–20m
- Zone 2 = 20–50m
- Zone 3 = 50m+

Status:

SELECTED

Validation Required:

- Distance accuracy benchmark

---

## Threat Assessment

### Selected Approach

Rule-Based Threat Engine

Inputs:

- Uniform Classification
- Weapon Category
- Distance Zone

Outputs:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

Reason:

Operational requirements are deterministic.

Status:

SELECTED

---

## Fire Detection

### Selected Approach

Independent Incident Pipeline

Output:

- HIGH Alert

Reason:

Fire events are operational incidents and shall not pass through the human threat assessment pipeline.

Status:

SELECTED

---

## Backend Architecture

### Selected Approach

Hybrid Architecture

Languages:

- Python
- C++

Python Responsibilities:

- Business logic
- Threat engine
- Alert manager
- API layer
- Event processing
- Configuration management

C++ Responsibilities:

- Performance-critical processing
- DeepStream integrations
- Custom GStreamer components
- Latency-sensitive modules

Reason:

Balances development speed and runtime performance.

Status:

SELECTED

---

## Database

### Selected Database

PostgreSQL

Reason:

- Production-grade reliability
- ACID compliance
- Strong indexing support
- JSON support
- Audit logging support
- Multi-user support
- Future central-server compatibility

Status:

SELECTED

---

## API Layer

### Selected Framework

FastAPI

Reason:

- Existing team experience
- High performance
- Strong typing
- OpenAPI support
- Easy frontend integration

Status:

SELECTED

---

## Frontend

### Selected Frontend

Existing Radar Eye Frontend

Responsibilities:

- Live monitoring
- Threat visualization
- Alert display
- Incident review
- System administration

Status:

SELECTED

---

## Alert Delivery

### Architecture

Pluggable Alert Channel Framework

Phase 1:

- UI Notifications

Future Channels:

- SMS
- Email
- WhatsApp
- GPIO Relay
- Audio Siren

Requirement:

Future channels must be added without modification to the Threat Engine.

Status:

SELECTED

---

## Recording Architecture

### Selected Strategy

Continuous Recording

and

Event Clip Recording

Continuous Recording:

- Full camera retention

Event Recording:

- Threat-triggered clips
- Fire-triggered clips

Status:

SELECTED

---

## Video Compression

### Selected Technology

NVIDIA NVENC

Framework:

- DeepStream
- GStreamer

Archive Codec:

- H.265 (HEVC)

Playback Codec:

- H.264 where required

Reason:

- Reduced storage usage
- Hardware accelerated
- Minimal CPU utilization
- Native Jetson support

Status:

SELECTED

---

## Logging

### Selected Approach

Structured Logging

Format:

- JSON

Reason:

- Easier debugging
- Easier monitoring
- Easier future SIEM integration

Status:

SELECTED

---

## Authentication

### Phase 1

Local Authentication

### Future

LDAP / Active Directory Integration

Status:

SELECTED

---

## Benchmark Validation Required

The following selections require validation before production approval:

- YOLO detector performance
- ViT classifier performance
- NvDCF tracking performance
- Distance estimation accuracy
- PostgreSQL performance
- DeepStream multi-camera scalability
- NVENC recording throughput

---

## Technology Selection Status

Current State:

TECHNOLOGY CANDIDATES SELECTED

Next Phase:

BENCHMARK PLANNING

Exit Criteria:

All selected technologies pass benchmark validation on Jetson AGX Orin 32GB deployment hardware.