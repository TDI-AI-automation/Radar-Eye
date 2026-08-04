# DeepStream Pipeline Specification

## Purpose

Define the end-to-end real-time video analytics pipeline.

This document is the authoritative specification for all DeepStream processing stages.

---

# Pipeline Overview

**Media Architecture Reset (ADR-028): Camera Ingestion is not part of
DeepStream.** DeepStream is one of several independent consumers of a
camera's encoded stream, not its owner. Everything below Stage 1 that
used to be described as "the DeepStream pipeline" is DeepStream's own
internal AI pipeline only — Camera Ingestion, Live Streaming, and
Recording are separate processes/services, each independently
subscribing to Stage 1's output.

```
Camera
    ↓
RTSP / H.264
    ↓
Stage 1: Camera Ingestion Service (rtspsrc → depay → h264parse)
    ↓
Encoded Split — every subsystem below subscribes independently,
                 to a locally re-published copy, never to the camera
                 directly (see Stage 1's own section for why)
    ├── Stage 1.5: Live Streaming Service
    │       ↓
    │   WebRTC → Browser (Live View channel)
    │
    ├── DeepStream (Stages 2-5.5: AI pipeline)
    │       ↓
    │   NVDEC → StreamMux → Primary GIE → NvDCF Tracker →
    │   Secondary GIE → Distance Estimation → Threat Engine →
    │   Incident Service → Event Bus → API Service → Frontend
    │       │
    │       └── OSD Overlay → H.264 Encode → re-published locally as
    │           "AI Streaming" → picked up by Stage 1.5's second,
    │           independent WebRTC channel (see Stage 5.5)
    │
    └── Stage 9: Recording Service
            ↓
        Continuous segments (independent of AI/Incident) +
        incident-triggered event clips (via Incident Service, as before)
```

DeepStream's fork (downstream of Secondary GIE, downstream of the only
metadata-extraction pass, `RuntimeAdapter`) is unchanged in shape — the
AI Streaming branch never re-runs inference, never re-parses
`NvDsBatchMeta`, and cannot affect the Inference Path. What changed is
everything *above* DeepStream: it no longer owns the camera connection,
Live Streaming is never inside its process, and its own encoded output
is one of several independent local publishers, not a direct WebRTC
peer connection.

**Governing principle: every media representation exists exactly
once.** The camera's original encoded H.264 exists once (Stage 1).
DeepStream's decoded NVMM frame exists once, inside DeepStream only.
DeepStream's OSD-annotated encoded frame exists once (Stage 5.5). Every
subsystem consumes one of those existing representations by
subscribing to it; no subsystem creates another copy of a
representation that already exists simply because it's convenient.
This is what keeps GPU/CPU/network cost bounded as Live Streaming,
Recording, and future analytics all attach to the same small set of
canonical streams.

---

# Stage 1: Camera Ingestion

Owner:

**Camera Ingestion Service** — an independent process. Never DeepStream
(ADR-028). This is the one and only subsystem that opens a real RTSP
connection to the physical camera.

Input:

- RTSP H.264

Camera Count:

- 20 Cameras

Deployment Target:

- 1 × Jetson AGX Orin 32GB (co-located with every other service, single
  node, per the project's deployment target — "independent process"
  means process/ownership isolation, not separate hardware)

Output:

- The camera's original, unmodified encoded H.264 access units, exactly
  once per camera — republished locally (loopback-only RTSP re-server,
  one per camera) for every subsystem below to consume independently.
  No subsystem holds its own connection to the physical camera.

Why one connection, republished, rather than one per consumer:

Empirically confirmed on this deployment's hardware: the physical
camera has a low concurrent-RTSP-session tolerance (observed refusing
new connections under connection churn, while still answering ICMP
ping). One upstream connection, many local subscribers, is a hard
requirement of this specific hardware, not a preference.

Requirements:

- Reconnect automatically
- Detect camera failures
- Emit CameraDisconnectedEvent
- Never decode, never touch NVDEC/CUDA/TensorRT — decode is DeepStream's
  concern alone (Stage 2)

---

# Stage 1.5: Live Streaming Service

Owner:

**Live Streaming Service** — an independent process. Never DeepStream
(ADR-028).

Purpose:

Deliver encoded H.264 to the operator's browser over WebRTC. Two
independent channels per camera, each a plain local RTSP subscriber:

- **Live View**: subscribes to Stage 1's republished output directly.
  No NVDEC, no inference, no TensorRT, no CUDA preprocessing, no
  dependency on AI state or DeepStream being alive at all. Lowest
  latency, never delayed by AI initialization or AI failure.
- **AI Streaming**: subscribes to DeepStream's own republished,
  OSD-annotated output (Stage 5.5). Independent of the Live View
  channel — losing this channel (e.g. DeepStream down) never affects
  Live View.

Chain (per channel):

`rtspsrc → depay → rtph264pay → webrtcbin`. No decode, no re-encode —
whichever upstream (Stage 1 or Stage 5.5) already produced the encoded
bytestream is passed straight to the browser.

Startup independence:

Comes up the moment Stage 1's endpoint for a camera is reachable —
never waits on DeepStream's model-loading time (see ADR-028's Problem
statement for the defect this fixes).

Failure isolation:

DeepStream crashing takes down only the AI Streaming channel; Live View
is unaffected. Live Streaming Service crashing affects only browser
delivery — AI, Recording, and Camera Ingestion are unaffected.

---

# Stage 2: Decode + StreamMux

Owner:

DeepStream. This is DeepStream's own first step -- a plain `rtspsrc`
subscription to Stage 1's locally re-published encoded stream (never a
direct connection to the physical camera; see ADR-028), followed by
NVDEC decode, only for cameras DeepStream is currently subscribed to
(AI enabled).

Component:

`nvv4l2decoder` (NVDEC) → `nvstreammux`

Responsibilities:

- Decode (NVDEC)
- Stream synchronization
- Batch generation
- Frame aggregation

Input:

- Multiple cameras' locally re-published encoded streams (Stage 1
  output), one `rtspsrc` subscription per camera DeepStream is
  currently consuming

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

Two independent consumers of this same encoded output, per ADR-028 —
"every media representation exists exactly once":

- Direct RTSP, `rtsp://<host>:<rtsp_port>/<stream_name>` (defaults
  `8554`/`radar-eye`, `configs/visualization.yaml`) — for VLC or any
  other RTSP client, unchanged diagnostic access.
- **AI Streaming**: the same encoded output, locally re-published the
  same way Camera Ingestion re-publishes Live View (Stage 1), picked up
  by Stage 1.5's Live Streaming Service as the browser-facing AI
  Streaming channel. DeepStream itself never runs WebRTC/`webrtcbin`
  code — `VisualizationManager` remains the sole external boundary,
  now serving both consumers off one encoded stream.

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

Owner:

**Recording Service** — an independent process/consumer of Stage 1's
Encoded Split, per ADR-028's principle 8: recording subscribes directly
to the encoded stream, never to AI/DeepStream output. Two distinct
recording modes, two distinct sources:

Continuous Recording:

Source: Stage 1 (Camera Ingestion's encoded output) directly —
independent of AI/Incident state, never interrupted by AI being
disabled or DeepStream being down.

Codec:

H.265

Retention:

30 Days

Event Clips (Evidence):

Source: Incident Service (Stage 8), as before — pre-event and
post-event buffer around an incident, extracted around the incident's
timestamp. Distinct concept from Continuous Recording above, not a
replacement for it.

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

Archive:

Retention/indexing/retrieval/export of both Continuous Recording
segments and Event Clips is **Archive Service's** responsibility, not
Recording Service's — Recording creates media, Archive manages its
lifecycle after creation (ADR-028 principle 9). See `docs/
DATABASE_SCHEMA.md` for the storage/table split.

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