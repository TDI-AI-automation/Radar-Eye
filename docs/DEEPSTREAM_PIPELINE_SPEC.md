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
internal AI pipeline only — Camera Ingestion and Recording are separate
processes/services, each independently subscribing to Stage 1's output.

**AI-Annotated-Only Video Output (ADR-030): DeepStream owns browser
video delivery.** ADR-028 additionally placed browser video delivery in
a second, independent Live Streaming Service with two channels (raw
"Live View" and AI-annotated "AI Streaming"). ADR-030 reverses that:
there is no raw/non-AI browser-facing video path and no separate Live
Streaming process. DeepStream is the sole producer of the one video
representation the browser ever receives — AI-annotated, encoded, and
written as low-latency MPEG-TS (`mpegtsmux` → `tcpserversink`) that
`apps.api` relays to authenticated browser WebSocket clients (ADR-032).
If DeepStream is unavailable, browser video is unavailable; this is an
accepted trade-off, not a gap (see ADR-030's Consequences).

**Low-Latency MPEG-TS Video Delivery (ADR-031/ADR-032): the
AI-annotated branch is fully persistent, never mutated by browser
activity.** ADR-030 kept WebRTC (`webrtcbin`) as the transport, which
required a dynamic per-browser-connection transport sub-branch (built
and torn down on every connect/reconnect) inside the same process
running PGIE/tracker/SGIE. ADR-031 replaced `webrtcbin` with `hlssink2`
(HLS) to eliminate that per-connection mutation; real-camera/real-
browser measurement then found HLS's glass-to-glass latency (~10s) was
unacceptable for real-time surveillance, so ADR-032 replaced `hlssink2`
with `mpegtsmux` → `tcpserversink` instead, keeping ADR-031's structural
lesson intact: one linear chain per camera, built once at camera-add
and torn down once at camera-remove, with no output tee and no dynamic
pad request/release of any kind. Browser connect/disconnect/refresh,
and how many browsers are watching, never reach DeepStream at all —
`tcpserversink` accepts any number of simultaneous TCP clients natively
(GStreamer's own multi-client fan-out), and `apps.api` opens one
persistent relay connection per browser viewer independently. Measured
glass-to-glass latency: ~0-1.2 seconds.

**Pipeline Decomposition (ADR-029): DeepStream is a pure CV engine.**
Everything downstream of metadata extraction — Distance Estimation,
Threat Engine evaluation, Incident lifecycle, Alerting, hardware
actuation, and evidence capture — is also not part of DeepStream.
DeepStream's own AI pipeline (Stages 2–5.5 below) ends at metadata
extraction and AI video output; it never calls into Calibration,
Threat Engine, Incident Service, Alert Service, or Hardware Action
Service in-process. Those run as independent processes, triggered only
by the metadata event DeepStream publishes (Stage 5.6).

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
    ├── DeepStream / AI Runtime (Stages 2-5.6: pure CV engine, ADR-029)
    │       ↓
    │   NVDEC → StreamMux → Primary GIE → NvDCF Tracker →
    │   Secondary GIE → Metadata Extraction (RuntimeAdapter, ADR-027)
    │       │
    │       ├── Stage 5.5: OSD Overlay → H.264 Encode → MPEG-TS
    │       │       (mpegtsmux → tcpserversink) → apps.api relays over
    │       │       WebSocket → Browser (ADR-030/ADR-032; the sole
    │       │       video representation the browser ever receives —
    │       │       no raw/non-AI channel exists)
    │       │
    │       └── Stage 5.6: ObservationEvent → published on the Event
    │               Bus (Stage 10) — DeepStream's last step; it does
    │               not call any downstream service directly, and this
    │               event carries observations only (detections,
    │               tracks, classifications, confidence, bounding
    │               boxes, timestamps, camera_id, frame_id) — never a
    │               decision (no threat level, alert, incident, or
    │               hostile/intruder field)
    │
    ├── Stage 6+7: Incident Service (Phase 5) — consumes Stage 5.6's
    │       ObservationEvent; owns Distance Estimation + Threat Engine
    │       evaluation as part of its own event handling; produces
    │       ThreatAssessmentEvent / HumanReviewItemCreatedEvent
    │       ↓
    │   Stage 8: Incident Service lifecycle → IncidentCreatedEvent /
    │   IncidentUpdatedEvent
    │       ↓
    │   Stage 8.5: Alert Service (Phase 6) → AlertRaisedEvent
    │       ↓
    │   Stage 8.6: Hardware Action Service (Phase 7) → GPIO / Siren /
    │   Floodlight / PTZ
    │
    ├── Stage 8.7: Evidence Service (Phase 8) — consumes Stage 5.6's
    │       ObservationEvent directly (not gated on Incident Service);
    │       when a full frame is needed, requests/captures it from
    │       Stage 5.5's diagnostic RTSP output (DeepStream gains no
    │       JPEG/image-writing responsibility) → SnapshotCreatedEvent
    │
    └── Stage 9+: Recording / Archive / Playback / Search / Export —
            POSTPONED per ADR-029, resumes after Phase 8. Design
            unchanged (ADR-017): continuous segments (independent of
            AI/Incident) + incident-triggered event clips (via
            Incident Service, as before)
```

DeepStream's fork (downstream of Secondary GIE, downstream of the only
metadata-extraction pass, `RuntimeAdapter`) is unchanged in shape — the
AI video-output branch never re-runs inference, never re-parses
`NvDsBatchMeta`, and cannot affect the Inference Path. What changed
relative to ADR-028 is: it no longer owns the camera connection (Camera
Ingestion still does — unchanged), but per ADR-030 it now *does* own
browser video delivery directly, writing low-latency MPEG-TS
(`mpegtsmux` → `tcpserversink`, ADR-032) rather than re-publishing for a
separate Live Streaming process to pick up.
What ADR-029 changes is everything *below* DeepStream's metadata
extraction: Distance Estimation, Threat Engine, Incident Service, Alert
Service, and Hardware Action Service are no longer in-process calls
made from inside DeepStream (superseding the RM-11 Phase 2
`ThreatEngineRuntimeAdapter` design) — they are separate processes
reacting to Stage 5.6's published `ObservationEvent`.

**Governing principle: every media representation exists exactly
once.** The camera's original encoded H.264 exists once (Stage 1).
DeepStream's decoded NVMM frame exists once, inside DeepStream only.
DeepStream's OSD-annotated encoded frame exists once per consumer
purpose (Stage 5.5: one encode for the browser MPEG-TS output, one for
the diagnostic RTSP output — see Stage 5.5's Output section). Every
subsystem consumes one of those existing representations by
subscribing to it; no subsystem creates another copy of a
representation that already exists simply because it's convenient.
This is what keeps GPU/CPU/network cost bounded as Recording and future
analytics attach to the same small set of canonical streams.

**Governing principle (ADR-029): every business decision is owned by
exactly one service.** Detection/tracking/classification is decided
once, in AI Runtime. Distance/zone and threat level are decided once,
in Incident Service. Alarm eligibility/dedup/escalation is decided
once, in Alert Service. Physical actuation is decided once, in
Hardware Action Service. No service re-derives a decision another
service already owns; no independently-deployed subsystem calls
another's internal logic directly (e.g. `IncidentService ->
AlertService.trigger()` in-process is prohibited) — every hand-off
downstream is by event, never by in-process call across these
boundaries. This does not restrict a subsystem's own in-process use of
a shared library it is the sole caller of (Incident Service invoking
`services/threat_engine`/`services/calibration` remains a library call
within one process, not a cross-subsystem call).

**Governing principle (ADR-029): AI Runtime publishes observations,
not decisions.** `ObservationEvent` (Stage 5.6) carries only what was
directly observed or measured — detections, tracks, classifications,
confidence, bounding boxes, timestamps, `camera_id`, `frame_id`. It
never carries a decision: no threat level, alert, incident, "intruder,"
escalation, or "hostile" field. Every decision is computed downstream
by the service that owns it.

**Governing principle (ADR-029): the Event Bus is transport only.**
Publish, subscribe, deliver — nothing else. No filtering, routing
logic, business rules, severity-based retries, transformation, or
enrichment inside the bus itself (see Stage 10).

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

(Stage 1.5, "Live Streaming Service," removed by ADR-030 — see Stage
5.5's Output section below for the browser video-output path DeepStream
now owns directly. Camera Ingestion, Stage 1 above, is unaffected.)

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

Two independent consumers, each with its own encode off the same
`sgie_tee` fork point (ADR-030 — DeepStream owns both; neither re-runs
inference or re-parses `NvDsBatchMeta`):

- **Diagnostic RTSP**: `rtsp://<host>:<rtsp_port>/<stream_name>`
  (defaults `8554`/`radar-eye`, `configs/visualization.yaml`) — for VLC
  or any other RTSP client, via `VisualizationManager`/
  `RtspStreamServer`, unchanged.
- **Browser video output (low-latency MPEG-TS, ADR-032)**:
  `apps/deepstream/app/live_stream/` — a second, independent
  OSD-annotated encode off `sgie_tee`, feeding
  `h264parse → mpegtsmux → tcpserversink` directly. Built exactly once
  per camera (at camera-add) and torn down exactly once (at
  camera-remove) — no output tee, no per-browser-connection sub-branch,
  no dynamic pad request/release of any kind; `idrinterval`/
  `iframeinterval` are both set to the encoder's own output-fps (~1s
  cadence), and `mpegtsmux`'s default PAT/PMT repeat interval (100ms)
  keeps the stream self-describing for a client connecting at any
  moment, together giving `tcpserversink` (`sync-method=next-keyframe`)
  a clean start point within about one GOP. `tcpserversink` accepts any
  number of simultaneous TCP clients natively (GStreamer's own
  multi-client fan-out); `apps.api` discovers each camera's assigned
  port via `camera_media_endpoints` (`subsystem="live_stream"`) and
  relays it to authenticated browser WebSocket clients
  (`GET /ws/cameras/{camera_id}/video`) — one dedicated TCP connection
  per browser viewer, a pure byte relay holding no state of its own; the
  browser plays it via `mpegts.js`. This is the only video
  representation the browser ever receives — there is no raw/non-AI
  channel and no separate Live Streaming process (ADR-030); DeepStream
  is never touched by a browser connecting, disconnecting, refreshing,
  or by how many browsers are watching (ADR-031/ADR-032). Measured
  glass-to-glass latency: ~0-1.2 seconds.

---

# Stage 5.6: ObservationEvent (ADR-029)

Owner:

**AI Runtime** (`apps/deepstream`) — this is DeepStream's last step.
Nothing downstream of this stage runs inside the DeepStream process.

Purpose:

Publish the per-frame detection/track/classification results
`RuntimeAdapter` already extracts (`FrameObservation` /
`DetectionObservation` / `TrackObservation`, ADR-027) as a formal event
on the Event Bus (Stage 10), instead of handing them to an in-process
orchestrator. This is the sole hand-off point between AI Runtime and
every downstream business service. Named for what it contains, not who
produced it — a future perception engine replacing DeepStream would
still publish `ObservationEvent`; only the documented Producer changes.

Input:

- `FrameObservation` / `DetectionObservation` / `TrackObservation`
  (already produced by `RuntimeAdapter`'s existing metadata-extraction
  pass — no new extraction logic, just a new publication step)

Output:

- `ObservationEvent` (payload schema: see `docs/EVENT_CONTRACTS.md`)

Observations only, never decisions (ADR-029 Governing Principle):

- Included: detections, tracks, classifications, confidence, bounding
  boxes, timestamps, `camera_id`, `frame_id`
- Excluded: threat level, alert, incident, "intruder," escalation,
  "hostile" — any field that represents a decision rather than a
  measurement. Those are computed downstream, never by AI Runtime.

Consumers:

- Incident Service (Stage 6+7+8)
- Evidence Service (Stage 8.7)

Explicitly prohibited beyond this stage, inside `apps/deepstream`
(ADR-029):

- Incident logic
- Alert logic
- Snapshot logic
- Database writes, beyond existing telemetry
- GPIO / siren / floodlight control
- Notification logic
- Any other business rule

---

# Stage 6+7: Distance Estimation + Threat Engine

Owner:

**Incident Service** (Phase 5) — these are no longer DeepStream
pipeline stages. They run as part of Incident Service's own handling
of the Stage 5.6 metadata event, calling `services/calibration` and
`services/threat_engine` unchanged (superseding the RM-11 Phase 2
`ThreatEngineRuntimeAdapter` design, which made these calls from inside
DeepStream — see ADR-029).

## Distance Estimation

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

## Threat Engine

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

Owner:

**Incident Service** (Phase 5) — an independent process, consuming
Stage 5.6's metadata event (via Stage 6+7's threat evaluation, in the
same process).

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

# Stage 8.5: Alert Service (ADR-029, new)

Owner:

**Alert Service** (Phase 6) — an independent process, consuming
`IncidentCreatedEvent` / `IncidentUpdatedEvent`.

Purpose:

Alert generation, severity, deduplication, escalation, operator
notification (UI / SMS / Email / WhatsApp — `docs/OPEN_QUESTIONS.md`
Q-005).

Owns:

The HIGH/FIRE alarm-eligibility rule (ADR-026), relocated here from an
undifferentiated "Alarm Service."

Generated Events:

- AlertRaisedEvent

---

# Stage 8.6: Hardware Action Service (ADR-029, new)

Owner:

**Hardware Action Service** (Phase 7) — an independent process,
consuming `AlertRaisedEvent`. Trigger source per ADR-012, amended by
ADR-029: Alert Service, not Threat Engine directly.

Purpose:

Physical actuation only — GPIO relay, siren, floodlight, PTZ preset,
future physical integrations (ADR-012's Supported Targets).

Prohibited:

Any eligibility, dedup, escalation, or notification decision — those
belong to Alert Service (Stage 8.5). Hardware Action Service only acts
on what it's told.

---

# Stage 8.7: Evidence Service (ADR-029, new)

Owner:

**Evidence Service** (Phase 8) — an independent process, consuming
`ObservationEvent` (Stage 5.6) directly. Not gated on Incident Service
or Alert Service state.

Purpose:

Full-frame snapshots, object/person crops (new capability — split out
of `services/recording`'s prior incident-level-only
`SnapshotCreatedEvent`), evidence storage, incident attachment.

Frame acquisition (metadata-only in, image out):

Evidence Service consumes `ObservationEvent` only — no video/frame data
flows to it directly, and AI Runtime gains no JPEG/image-writing
responsibility. When `ObservationEvent` indicates a snapshot is
warranted, Evidence Service requests/captures the actual frame from
Stage 5.5's diagnostic RTSP output (the same OSD-annotated
representation the browser video-output branch also derives from,
ADR-030), never a new representation created by DeepStream for this
purpose — per the "every media representation exists exactly once"
principle:

```
ObservationEvent
      ↓
Evidence Service (decides a snapshot is warranted)
      ↓
requests/captures a frame from Stage 5.5's diagnostic RTSP output
      ↓
writes the JPEG, emits SnapshotCreatedEvent
```

Generated Events:

- SnapshotCreatedEvent

Not this stage's responsibility:

Event clips (video) — those remain bundled with the postponed
Recording Service (Stage 9+), produced only once Recording resumes.

---

# Stage 9+: Recording Service (POSTPONED per ADR-029)

Status:

Phase 9+ — deferred until Phase 8 (Evidence Service) is complete. Part
of the locked Phase 3→4→5→6→7→8→9+ sequence; resumes as originally
specified below, not redesigned.

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

Event Clips (video):

Source: Incident Service (Stage 8), as before — pre-event and
post-event buffer around an incident, extracted around the incident's
timestamp. Distinct concept from Continuous Recording above, not a
replacement for it. Snapshots are no longer part of this service's
scope — see Stage 8.7 (Evidence Service), which produces them
independently of Recording's postponement.

Evidence Types:

- Event Clips

Clip Policy:

Pre-event buffer
+
Post-event buffer

Generated Events:

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

Status (ADR-029, Phase 4):

Production, cross-process transport — replaces the in-process-only
`InProcessEventBus` (RM-04) now that AI Runtime, Incident Service,
Alert Service, Hardware Action Service, Evidence Service, and Recording
(once resumed) each run as independent OS processes, per ADR-028's
process-separation model. The `EventBus` abstract contract itself is
unchanged; only the concrete transport is swapped, per RM-04's own
standing note that this was always the intended extension point.

Consumers:

- API Service
- AI Runtime (publishes only — Stage 5.6)
- Incident Service
- Alert Service
- Hardware Action Service
- Evidence Service
- Recording Service (once resumed)

Transport:

Internal Event Bus

Requirements:

- Immutable events
- Versioned contracts
- Transport only (ADR-029 Governing Principle) — publish, subscribe,
  deliver, nothing else. Explicitly prohibited inside the bus:
  filtering, routing logic, business rules, severity-based retries,
  transformation, enrichment. Any of those belong to the consuming
  service, never to the bus.

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