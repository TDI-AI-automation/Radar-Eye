# Radar Eye Architecture Decision Records

Purpose:

Track all architecture decisions.

No architecture decision is considered final unless documented in this file.

---

# ADR-001

Decision:

DeepStream as mandatory video processing framework.

Status:

ACCEPTED

Reason:

Production-grade GPU accelerated video analytics on NVIDIA Jetson.

---

# ADR-002

Decision:

TensorRT as mandatory production inference runtime.

Status:

ACCEPTED

Reason:

Required for real-time edge inference performance.

---

# ADR-003

Decision:

Offline-First Architecture.

Status:

ACCEPTED

Reason:

Military deployments cannot depend on internet connectivity.

---

# ADR-004

Decision:

Air-Gapped Deployment Support.

Status:

ACCEPTED

Reason:

Military deployment requirement.

---

# ADR-005

Decision:

Zero-Copy Processing Preferred.

Status:

ACCEPTED

Reason:

Reduce memory transfer overhead and maximize throughput.

---

# ADR-006

Decision:

PostgreSQL selected as primary database.

Status:

ACCEPTED

Reason:

Structured relational data, auditability, operational simplicity, offline deployment support.

---

# ADR-007

Decision:

Internal Event-Driven Architecture.

Status:

ACCEPTED

Reason:

Loose coupling between DeepStream, Threat Engine, Incident Service, Recording Service, API Service and future components.

---

# ADR-008

Decision:

Metadata-only storage architecture.

Status:

ACCEPTED

Reason:

Store incidents, evidence metadata, audit history and configuration.

Do not store frames, detections, tracks or per-frame analytics.

---

# ADR-009

Decision:

Authentication Architecture.

Status:

ACCEPTED

Initial State:

Local users.

Future State:

LDAP / Active Directory integration.

Reason:

Military deployments require local operation while preserving future enterprise integration.

---

# ADR-010

Decision:

Single Node Deployment Architecture.

Status:

ACCEPTED

Deployment:

1 × Jetson AGX Orin 32GB

Camera Capacity:

20 Cameras

Reason:

Simpler deployment and operations.

---

# ADR-011

Decision:

Frontend Video Delivery Strategy.

Status:

ACCEPTED

Strategy:

Backend-controlled video delivery.

Realtime metadata delivered via WebSocket.

Reason:

Centralized access control and simplified frontend integration.

---

# ADR-012

Decision:

Alarm Integration Protocol.

Status:

ACCEPTED

Supported Targets:

- Relay Controller
- GPIO Relay
- Siren
- Beacon Light

Trigger Source:

Threat Engine

Reason:

Hardware independence.

---

# ADR-013

Decision:

Tracker Selection.

Status:

ACCEPTED

Selected Tracker:

NvDCF

Reason:

DeepStream native integration and persistent tracking performance.

---

# ADR-014

Decision:

Primary Detector Selection.

Status:

ACCEPTED

Selected Detector:

YOLO26M Weapon Detector

Model:

models/yolo26m_weapon.pt

Reason:

Project benchmark selection.

---

# ADR-015

Decision:

Threat Engine Architecture.

Status:

ACCEPTED

Type:

Rule-Based Threat Evaluation Engine.

Inputs:

- Weapon Type
- Uniform Classification
- Distance Zone

Outputs:

- Threat Level
- Incident Decisions
- Alarm Decisions

Reason:

Deterministic and auditable behavior.

---

# ADR-016

Decision:

Distance Estimation Strategy.

Status:

ACCEPTED

Method:

Ground Plane Projection

Calibration:

- Installer Calibration
- Operator Recalibration

Reason:

Operational simplicity and explainability.

---

# ADR-017

Decision:

Recording Strategy.

Status:

ACCEPTED

Recording:

Continuous Recording

Evidence:

Event Clip Extraction

Codec:

H.265

Retention:

30 Days

Reason:

Operational investigation requirements.

---

# ADR-018

Decision:

Backend Framework.

Status:

ACCEPTED

Framework:

FastAPI

Reason:

High performance, type safety and API-first development.

---

# ADR-019

Decision:

Deployment Hardware.

Status:

ACCEPTED

Hardware:

NVIDIA Jetson AGX Orin 32GB

Reason:

Project deployment target.

---

# ADR-020

Decision:

Frontend Reuse Strategy.

Status:

ACCEPTED

Frontend Repository:

https://github.com/CodeHub1443/radar-eye-command

Strategy:

Reuse existing frontend.

Replace mock data with APIs and WebSocket streams.

Reason:

Reduce development time.

---

# ADR-021

Decision:

Threat Escalation Policy.

Status:

ACCEPTED

Rules:

HIGH:
- 3 consecutive frames -> ThreatAssessmentEvent
- 1 second sustained -> Incident
- 3 seconds sustained -> Alarm

MEDIUM:
- 2 seconds sustained -> Incident

LOW:
- Dashboard only

Fire:
- Immediate HIGH
- Immediate Incident
- Immediate Alarm

Reason:

Reduce false positives while maintaining operational responsiveness.

---

# ADR-022

Decision:

Threat De-escalation Policy.

Status:

ACCEPTED

Rules:

HIGH:
- Threat absent for 10 seconds

MEDIUM:
- Threat absent for 5 seconds

LOW:
- Threat absent for 3 seconds

Reason:

Prevent oscillation and alert fatigue.

---

# ADR-023

Decision:

Human Review Workflow.

Status:

ACCEPTED

Trigger:

Uniform Classification = Unknown

Action:

Create HUMAN_REVIEW item.

Operator Actions:

- Confirm Military
- Confirm Civilian
- Escalate
- Dismiss

Reason:

Prevent automatic decisions on uncertain classifications.

---

# ADR-024

Decision:

Incident Creation Policy.

Status:

ACCEPTED

HIGH:
- Incident Created

MEDIUM:
- Incident Created

LOW:
- No Incident

ALLY:
- No Incident

OBSERVE:
- No Incident

HUMAN_REVIEW:
- No Incident

Reason:

Reduce operational noise.

---

# ADR-025

Decision:

Incident Deduplication Policy.

Status:

ACCEPTED

Rule:

1 Track = 1 Active Incident

Incident Ends When:

- Track Lost > 10 Seconds
OR
- Operator Closes Incident

Reason:

Prevent duplicate incidents.

---

# ADR-026

Decision:

Alarm Trigger Policy.

Status:

ACCEPTED

HIGH:
- Alarm Eligible

MEDIUM:
- No Alarm

LOW:
- No Alarm

ALLY:
- No Alarm

OBSERVE:
- No Alarm

HUMAN_REVIEW:
- No Alarm

Fire:
- Immediate Alarm

Reason:

Prevent unnecessary alarm activations.

---

# ADR-027

Decision:

DeepStream Runtime Adapter as Anti-Corruption Layer.

Status:

ACCEPTED

Boundary:

The Runtime Adapter (apps/deepstream/app/runtime_adapter.py) is the sole boundary between the NVIDIA DeepStream/GStreamer SDK and the application domain.

Prohibited Beyond Runtime Adapter:

- pyds
- NvDsBatchMeta
- NvDsFrameMeta
- NvDsObjectMeta
- NvDsClassifierMeta
- NvDsUserMeta
- Gst.Buffer
- Gst.Sample
- Any other DeepStream- or GStreamer-specific runtime type

Permitted Beyond Runtime Adapter:

Repository-native domain objects only.

Examples:

- FrameObservation
- DetectionObservation
- TrackObservation
- DistanceEstimate
- ThreatAssessmentEvent
- HumanReviewItemCreatedEvent
- CameraDisconnectedEvent
- SystemEvent

Runtime Adapter Owns:

- Metadata extraction
- Coordinate conversion
- Timestamp normalization
- Confidence normalization
- Class mapping
- SDK-specific error handling

Application Services Own:

- Business rules
- Threat assessment
- Calibration semantics
- Incident creation
- Alarm generation
- Event publication

Import Restriction:

No subsystem outside apps/deepstream/ may import:

- pyds
- gi.repository.Gst
- gi.repository.GLib
- Any DeepStream helper library

Scope:

Applies to all present and future milestones and subsystems, not RM-11 alone.

Reason:

Isolates the application domain from a specific inference/runtime SDK. If the inference backend is replaced (TensorRT, Triton, ONNX Runtime, OpenVINO, CPU inference, simulation, recorded playback, etc.), only the Runtime Adapter requires modification; every other subsystem remains unchanged.

---

# ADR-028

Decision:

Media Architecture Reset -- Camera Ingestion and Live Streaming are separate processes from DeepStream.

Status:

ACCEPTED

Supersedes:

DEEPSTREAM_PIPELINE_SPEC.md's Stage 1 (Camera Ingestion), to the extent it framed ingestion as owned by DeepStream. CAMERA_RUNTIME_LIFECYCLE.md Section 7's prior direction that Live Streaming/WebRTC be built as an internal extension of DeepStream's Media Publisher.

Problem:

A live pipeline trace (hardware-measured) proved that DeepStream owning camera ingestion inside its own Gst.Pipeline is not merely inelegant -- it is a reproducible production defect. GstBin/GstPipeline state changes walk every child element serially, on one thread, inside one blocking set_state() call. nvinfer (PGIE/SGIE) performs synchronous TensorRT engine deserialization inside that walk. Measured: SGIE 4.9s + PGIE 4.3s = 9.18s before set_state() returns, during which rtspsrc/depay -- part of a topologically unrelated branch with zero GStreamer link to PGIE/SGIE -- could not advance past READY, because they were queued behind PGIE/SGIE in the same bin's child-iteration order. Live video was architecturally hostage to AI model-loading time, despite having no data dependency on it.

Decision:

Camera ingestion (rtspsrc -> rtph264depay -> h264parse) is owned by a new, independent Camera Ingestion Service -- never by DeepStream. Camera Ingestion holds exactly one upstream RTSP connection per camera and republishes the encoded H.264 locally (loopback RTSP re-server) for every subsystem to consume independently. DeepStream becomes a pure AI consumer: NVDEC -> nvstreammux -> PGIE -> Tracker -> SGIE -> OSD -> AI Streaming output. It owns AI and nothing else -- not camera connectivity, not Live Streaming. Live Streaming (WebRTC delivery to the browser, for both Live View and AI Streaming) is a new, independent Live Streaming Service, never part of the DeepStream process.

Operational constraint informing this decision:

The physical camera in this deployment has a low concurrent-RTSP-session tolerance, independently observed refusing new connections after heavy connection churn while remaining reachable via ICMP. Camera Ingestion's one-upstream-connection-per-camera design is required by this constraint, not merely preferred -- any design opening more independent RTSP connections to the camera than today would make this worse.

Startup independence:

Live Streaming's and DeepStream's startup sequences are independent of each other. Neither blocks on the other's readiness. Model loading may take any amount of time; it must never delay Live View.

Failure isolation:

If DeepStream crashes, Live View and Recording continue. If Live Streaming fails, AI continues. If Recording fails, Live View and AI continue. Camera Ingestion is the one accepted single point of failure for all consumers, mitigated by keeping it maximally simple (no AI/CUDA/TensorRT).

Reason:

Live video delivery must never be coupled to AI subsystem initialization time or AI subsystem failure. The previous architecture made this impossible to guarantee by construction, not just by configuration.