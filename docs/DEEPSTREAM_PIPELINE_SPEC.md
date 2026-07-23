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
[fork: tee — visualization.enabled gates whether this fork exists at all]
    ├── Inference Path (always present)
    │       ↓
    │   Distance Estimation
    │       ↓
    │   Threat Engine
    │       ↓
    │   Incident Service
    │       ↓
    │   Recording Service
    │       ↓
    │   Event Bus
    │       ↓
    │   API Service
    │       ↓
    │   Frontend
    │
    └── Visualization Path (optional, RM-11.SIV — see Stage 5.5)
            ↓
        OSD Overlay (NvDsDisplayMeta)
            ↓
        H.264 Encode
            ↓
        RTSP Output
            ↓
        Operator (VLC / any RTSP client)

The fork point is downstream of Secondary GIE and downstream of the only
metadata-extraction pass (`RuntimeAdapter`, which runs off a pad probe
before the fork) — the Visualization Path never re-runs inference, never
re-parses `NvDsBatchMeta`, and cannot affect what the Inference Path
receives. When `visualization.enabled: false` (default), the fork does not
exist — Secondary GIE links directly to the pipeline terminator, identical
to pre-RM-11.SIV-visualization behavior.

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

# Stage 5.5: Visualization Path (RM-11.SIV, optional)

Purpose:

Operator-visible video output. Renders directly from this pipeline's own
PGIE/NvDCF/SGIE results — no second inference pass, no OpenCV, no duplicate
metadata extraction.

Component:

`apps/deepstream/app/visualization/` — `VisualizationManager`,
`VisualizationPipelineBuilder`, `DeepStreamOverlayRenderer`,
`RtspStreamServer`.

Fork point:

`tee` immediately after Secondary GIE. Exists only when
`configs/visualization.yaml`'s `enabled: true`. Absent otherwise — Secondary
GIE links directly to the pipeline terminator, byte-for-byte identical to
the pre-visualization pipeline.

Chain (visualization branch only):

`tee → queue("viz-queue") → nvvideoconvert → capsfilter(RGBA) → [annotate
probe] → nvdsosd → nvvideoconvert → capsfilter(NV12) → nvv4l2h264enc →
h264parse → rtph264pay → udpsink → RtspStreamServer (RTSP proxy)`.

Backpressure policy:

`viz-queue` is `leaky=2` (drops the *oldest* buffered frame, never the
newest) with `max-size-buffers=4`, `max-size-bytes=0`, `max-size-time=0` —
bounded purely by buffer count. This guarantees the visualization branch can
never block the `tee`'s `push()`, and therefore can never apply backpressure
onto the Inference Path sharing the same `tee`. If the encoder/RTSP client
falls behind, visualization frames are dropped; inference throughput is
unaffected. Measured impact: see `docs/SIV_BASELINE.md`'s Visualization OFF
vs. ON table.

Metadata immutability (hard rule):

The annotate probe (`DeepStreamOverlayRenderer.probe_callback`) may write
only `obj_meta.rect_params`/`text_params` and add new `NvDsDisplayMeta`
objects — the fields DeepStream defines specifically for on-screen display.
It must never write `class_id`, `obj_label`, `confidence`, `object_id`
(track ID), or any other detection/classification/tracking field. The
Visualization Path is strictly read-only with respect to inference
metadata — it consumes what PGIE/NvDCF/SGIE/`RuntimeAdapter` produced, never
mutates it, and nothing downstream of the fork on the Inference Path can
observe any effect from the Visualization Path existing at all.

Failure isolation:

Any failure constructing or starting the Visualization Path (missing
element, RTSP port already bound, etc.) is caught at the call site in
`apps/deepstream/app/pipeline/builder.py`, logged, and converted into
`VisualizationManager.health()` reporting `enabled=True, running=False,
reason=<...>`. The Inference Path is never affected — verified on real
hardware, see `docs/SIV_BASELINE.md`.

Output:

RTSP, `rtsp://<host>:<rtsp_port>/<stream_name>` (defaults `8554`/`radar-eye`,
`configs/visualization.yaml`). Future WebRTC/HLS output is an internal
addition to this same package (`VisualizationManager` is the sole external
boundary) — not implemented in RM-11.SIV.

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