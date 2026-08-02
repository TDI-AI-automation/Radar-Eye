# DeepStream Pipeline Specification

## Purpose

Define the end-to-end real-time video pipeline: ingestion, live streaming,
recording, AI analytics, and snapshot generation.

This document is the authoritative specification for pipeline *topology* and
*stages*. It describes **Camera Runtime v1** as it actually exists in
`apps/deepstream/app/` today, plus the extension points approved for future
work. It does not duplicate `docs/CAMERA_RUNTIME_LIFECYCLE.md`'s startup
sequence, dependency graph, ownership table, or shutdown order — that
document is the authoritative "read this instead of the source" reference
for the runtime's internal construction and lifecycle; this document is the
authoritative reference for the *pipeline graph itself* (what feeds what).

---

# Pipeline Overview

```
                    Camera
                       │
                  RTSP Source (rtspsrc)
                       │
                    Depay (rtph264depay)
                       │
                Depay-tee  ⚠ designed, not yet implemented — see Stage 2/3
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
  Parser (dedicated)            Parser (shared)  ⚠ new
  h264parse                     h264parse
        │                             │
   Decode (nvv4l2decoder)        Tier 0 tee  ⚠ new
        │                    ┌────────┴────────┐
   Tier 1 tee                ▼                 ▼
   (Frame Distributor,  Live Streaming     Recording
   built)               (WebRTC, planned)  (planned)
        │
   ┌────┼────────┬─────────┐
   │    │        │         │
   ▼    ▼        ▼         ▼
(→AI  AI valve  Snapshot  Other
 branch)  │     (planned)
          ▼
     AI branch:
     PGIE → NvDCF → SGIE
          │
   ┌──────┴──────┐
   ▼             ▼
Decision      Tier 2 tee
Pipeline      (post-SGIE, AI-gated)
(Distance          │
 Estimation    ┌────┴────┐
 → Threat       ▼         ▼
 Engine    Visualization  Tier 2
 → Incident (AI Streaming, consumers
 /Alarm     built, RTSP)  (planned)
 → Event
 Bus)
```

This diagram is the architecture. Every branch exists because it represents
a real system responsibility, whether or not it has a consumer today. Do not
collapse branches, and do not remove the "Other" expansion point merely
because nothing is attached to it yet.

**Why the parser is duplicated, not shared across all three of Decode/Live
Streaming/Recording** (a corrected finding — an earlier draft of this
document proposed one shared parser before a single tee; investigate before
building either shape again): the current, hardware-validated decode chain
(`ingestion/source.py`) links `depay` directly to `parse` directly to
`decoder`, with no element between `parse` and `decoder`. Real-world evidence
(NVIDIA Developer Forums, not assumption) shows inserting a `tee` between an
`h264parse` and its consuming `nvv4l2decoder` has caused complete pipeline
stalls on some systems — a risk specific to `nvv4l2decoder`'s own
adjacency requirements, not a general problem with sharing a parsed stream
(NVIDIA's own Smart Video Record shares one parser across branches safely —
but its tap never touches `nvv4l2decoder`). The decode branch therefore
keeps its own dedicated, directly-adjacent parser, unchanged from today.
Live Streaming and Recording — neither of which touches `nvv4l2decoder` —
safely share one separate parser instance between themselves, matching
NVIDIA's own pattern for non-decode encoded-stream consumers.

**Built and hardware-validated today:** RTSP ingestion through Decode, Tier 1
(Frame Distributor), the AI branch (PGIE/NvDCF/SGIE), the Decision Pipeline,
Tier 2's topology, and Visualization (AI Streaming).

**Designed, approved, not yet implemented:** the depay-tee, dedicated
decode-branch parser, Tier 0 (pre-decode tee for Live Streaming and
Recording), `Tier0Publisher`/`Tier0FrameConsumer` (a third `_TieredPublisher`
instance, mirroring `Tier1Publisher`/`Tier2Publisher` exactly — not a new
abstraction), the Live Streaming consumer, the Recording consumer, and the
Snapshot consumer. These are documented here as the target shape —
implementation requires its own separate approval per milestone/ticket, not
this document alone.

---

# Production Design Principle: Consume the Earliest Sufficient Representation

Whenever possible, a consumer attaches at the earliest point in the pipeline
that already carries the representation it needs — never later than that.

- Never decode something a consumer does not need decoded.
- Never encode something a consumer already accepts in its current, encoded
  form.

Examples already governing this document's stage placement:

| Subsystem | Representation consumed | Why |
|---|---|---|
| Live Streaming | Encoded H.264 (Tier 0) | Browser/WebRTC accepts encoded video directly — decoding would be pure waste. |
| Recording | Encoded H.264 (Tier 0) | Storage wants compressed bytes; decoding then re-encoding for storage would add GPU cost and quality loss for no benefit. |
| AI | Decoded frames (post-Decode) | Inference needs pixel data — this is the one consumer that requires decode. |
| Snapshot | Decoded frames (Tier 1) | A JPEG encoder needs pixel data, not compressed H.264 — Tier 1's already-decoded frames are the earliest sufficient representation for this consumer specifically. |

This principle drives every future pipeline extension decision, not just the
four above.

---

# Camera Runtime v1 (built)

The production runtime (`apps/deepstream/app/main.py` →
`DeepStreamRuntime` in `runtime.py`). Full construction order, dependency
graph, resource ownership, shutdown order, and operational invariants:
`docs/CAMERA_RUNTIME_LIFECYCLE.md`. Summary of the components this document's
pipeline stages below depend on:

- **Source Manager** (`ingestion/source.py`) — builds one camera's decode
  bin. The only module that requires real Jetson/DeepStream hardware to
  exercise.
- **Frame Distributor / Tier 1** (`pipeline/frame_distributor.py`) — a `tee`
  positioned between the decoder and the AI valve, so Tier 1 is structurally
  independent of AI enable/disable state.
- **AI valve** — the element `RuntimeSupervisor` exclusively mutates to gate
  a camera's AI branch on/off. `RuntimeSupervisor` is the *only* component
  permitted to touch it.
- **Desired State Synchronizer** — reconciles the Camera Registry's
  (database) `ai_enabled`/`lifecycle_state`/`recording_enabled` intent
  against runtime reality, dispatching the minimal `add_source`/
  `remove_source`/`enable_ai`/`disable_ai` actions. Owns no pipeline
  mutation itself for AI state — it decides *direction*, `RuntimeSupervisor`
  converges it.
- **Media Publisher** (`media_publisher/`) — owns Tier 1 and Tier 2 consumer
  lifecycle (register/unregister/attach/detach) behind one shared,
  failure-isolated `ConsumerRegistry` per tier, via the `Tier1FrameConsumer`/
  `Tier2FrameConsumer` protocols (`media_publisher/interfaces.py`). Ships
  with zero default subscribers by design — this is the attachment point for
  every "planned" consumer in this document. Tier 0 (Stage 3) extends this
  the same way: a third `Tier0Publisher(_TieredPublisher[Tier0FrameConsumer])`
  reusing the existing `_TieredPublisher` base's registry/attach/detach/
  backpressure/failure-isolation machinery unchanged — not a new
  abstraction, the same one Tier 1/Tier 2 already use, applied a third time.
- **Runtime Adapter** (`ai_runtime/` — `RuntimeAdapter` +
  `ThreatEngineRuntimeAdapter`) — the ADR-027 anti-corruption layer; the
  sole `pyds`/`NvDsBatchMeta`/`NvDsFrameMeta`/`NvDsObjectMeta` boundary in
  the repository.
- **Visualization** (`visualization/`) — the AI Streaming subsystem (Stage
  6 below).
- **SIV infrastructure** (`siv/`, `heartbeat_registry.py`,
  `stage_logging.py`, `pipeline_trace.py`) — validation/observability, not
  part of the pipeline graph itself.

All of the above are **stable production architecture, hardware-validated,
and not to be redesigned.** Changes to them require an explicit, separate
architectural decision, not something this document's extension points imply.

---

# Stage 1: Camera Ingestion

Input:

- RTSP H.264

Camera Count:

- 20 Cameras

Deployment Target:

- 1 × Jetson AGX Orin 32GB

Requirements:

- Reconnect automatically (per-camera `ReconnectPolicy`, exponential
  backoff, one camera's failure never affects another's)
- Detect camera failures
- Emit `CameraDisconnectedEvent`

---

# Stage 2: Depay ⚠ tee point designed, not implemented

Component (built, unchanged):

`rtph264depay`

Component (designed, not implemented):

A `tee` (`depay-tee`) immediately after `rtph264depay`, before any parser —
**not** after a shared parser (see the Pipeline Overview's "Why the parser
is duplicated" note above; a real, hardware-reported `nvv4l2decoder`-behind-
tee stall risk rules out the shared-parser-before-tee shape this document
originally proposed).

Branches off `depay-tee`:

1. **Decode-bound**: its own dedicated `h264parse` (`config-interval=1`,
   explicit `stream-format=avc`), linked directly to `nvv4l2decoder` — this
   is exactly today's existing `depay.link(parse); parse.link(decoder)`
   adjacency (`ingestion/source.py`), unchanged. Feeds Stage 4 (Decode).
2. **Tier-0-bound**: a second, separate `h264parse` instance
   (`config-interval=1`), shared between Live Streaming and Recording only
   — neither touches `nvv4l2decoder`, so they don't carry the stall risk
   the decode branch's dedicated parser exists to avoid. Feeds Stage 3
   (Tier 0).

Per-branch `queue` (bounded, leaky) required on both, per GStreamer's own
tee documentation — a blocked branch otherwise stalls every other branch
sharing the tee.

---

# Stage 3: Tier 0 — Original Stream Fork ⚠ designed, not implemented

Purpose:

Fork the parsed-but-still-encoded H.264 elementary stream (via Stage 2's
Tier-0-bound parser) for consumers that must never pay a decode/re-encode
cost — Live Streaming, and Recording (Stage 7).

Component:

`tee` fed by Stage 2's Tier-0-bound `h264parse` instance (not the
decode-bound one — see Stage 2). Every branch off it gets its own `queue`
(GStreamer's own documented requirement — a blocked branch otherwise stalls
every other branch sharing the tee).

Why here and not later:

- Depay→pay (not decode→encode) is the only way to hand the same compressed
  bytes to a second, independent RTP session (WebRTC's) — RTSP and WebRTC
  RTP sessions are structurally separate (different SSRC/sequence spaces,
  WebRTC additionally requires SRTP/DTLS); raw RTP packets cannot be forwarded
  directly between them.
- Tapping before decode, not after (i.e. not reusing Tier 1), is what makes
  this branch add zero GPU work and the minimum possible copy size —
  compressed kilobytes-per-frame versus decoded megabytes-per-frame.

Consumers (see Stages 6 area below for the built ones; these are planned):

- Live Streaming (Stage 3a)
- Recording (Stage 7)

---

# Stage 3a: Live Streaming ⚠ designed, not implemented

Purpose:

Lowest-latency operator video view — the camera's original stream, exactly
as encoded, exists regardless of AI state or Recording state.

Input:

- Tier 0 (Stage 3)

Processing:

`queue(leaky, bounded)` → `rtph264pay(config-interval=1)` → `webrtcbin` (or
an intermediate WebRTC media server, if one is introduced later — the
architectural subsystem is "Live Streaming," the transport is not fixed to
WebRTC specifically; see Architecture Constraints).

Prohibited on this path:

- Decode
- Re-encode
- CUDA processing
- Colorspace conversion

Requirement:

Must never be interrupted by AI enable/disable for that camera, and must
never be blocked by (or block) the AI/decode path — both guaranteed by
per-branch `queue`s at every tee from Stage 2 onward, and by sharing no
element with the decode path at any point (separate parser instance from
`depay-tee`, Stage 2, all the way through).

---

# Stage 4: Decode

Component:

NVDEC (`nvv4l2decoder`)

Purpose:

Produce GPU decoded frames for every consumer that needs pixel data (Tier
1's Recording/Snapshot/Other consumers, and the AI branch).

Input:

- Parsed H.264 elementary stream (Stage 2's dedicated decode-bound
  `h264parse`, directly adjacent — unchanged from today's code)

Output:

- GPU decoded frames

---

# Stage 5: Tier 1 — Frame Distributor (built)

Component:

`pipeline/frame_distributor.py` — a `tee` positioned between the decoder and
the AI valve, per camera.

Purpose:

Fan decoded frames out to independent consumers without coupling them to AI
state or to each other.

Input:

- GPU decoded frames (Stage 4)

Requirement:

Each consumer operates independently via `Tier1FrameConsumer.on_raw_frame`,
registered through Media Publisher. A stopped, absent, or failed consumer
must not affect the others or the AI path — enforced by the tee's bounded,
leaky terminator branch existing regardless of whether any consumer is
attached (see Camera Runtime v1 section above).

Consumers:

- AI valve → AI branch (Stage 6, built)
- Snapshot ⚠ designed, not implemented — see Stage 8 (decoded frames, not
  Tier 0 — see the Production Design Principle above)
- Other — expansion point, no consumer today; do not remove

Recording is **not** a Tier 1 consumer — it consumes Tier 0 (Stage 3,
encoded), not Tier 1 (decoded), per the Production Design Principle above
and the explicit architectural rule this establishes: encoded-storage
consumers attach at the earliest sufficient (encoded) representation.

---

# Stage 6: AI Branch (built)

Frame Source:

Tier 1, gated by the AI valve — `RuntimeSupervisor` is the only component
permitted to mutate it, driven by Desired State Synchronization from the
Camera Registry's `ai_enabled` column (the Operator Experience section
below).

## Stage 6a: DeepStream (Detection + Classification)

Purpose:

Weapon/person detection and uniform classification.

Primary Detector:

Model: `models/yolo26m_weapon.pt` · Runtime: TensorRT (ADR-002, ADR-014)

Supported Classes:

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

Secondary Classifier (Uniform):

Model: `models/vit_48k_binary.pth` · Runtime: TensorRT · Input: person crop
from tracker output.

Output Classes:

- military
- civilian
- unknown

## Stage 6b: Tracking

Component:

NvDCF (ADR-013)

Requirements:

- Support 20+ simultaneous persons
- Stable track persistence
- Re-identification support where available

## Stage 6c: Decision Pipeline (built, unchanged)

Extracted from the raw inference buffer by `RuntimeAdapter` (the sole
`pyds`-touching module, ADR-027) into `FrameObservation`s, then routed by
`ThreatEngineRuntimeAdapter`:

### Distance Estimation

Method: Ground Plane Projection (ADR-016). Inputs: Track Position, Camera
Calibration. Outputs: Distance, Zone (`zone_1` 0–20m, `zone_2` 20–50m,
`zone_3` 50m+). Owning Service: `services/calibration` (RM-05).

### Threat Engine

Inputs: Weapon Type, Uniform Class, Distance Zone. Outputs: Threat Level
(ALLY/OBSERVE/LOW/MEDIUM/HIGH/HUMAN_REVIEW), Human Review Decision, Incident
Decision, Alarm Decision. Generated Events: `ThreatAssessmentEvent`,
`HumanReviewItemCreatedEvent`. Owning Service: `services/threat_engine`
(RM-06).

### Incident Service / Alarm Service

Incident creation, updates, deduplication (1 track = 1 active incident).
Generated Events: `IncidentCreatedEvent`, `IncidentUpdatedEvent`. Owning
Service: `services/incident_service` (RM-07, also owns Alarm Service, RM-10)
— `AlarmService` is a long-lived singleton owned by `DeepStreamRuntime`
(its in-memory alarm-record state must persist across calls).

## Stage 6d: Tier 2 (built topology, zero consumers today)

Component:

`nvstreamdemux`, built once camera-independently; `Tier2Publisher` builds/
tears down each camera's own branch off it inline from `add_source()`/
`remove_source()`.

Availability:

Automatic, not a decision this layer makes — a camera whose AI valve is
closed never feeds PGIE/Tracker/SGIE at all, so its `nvstreamdemux` output
simply receives nothing while AI-disabled.

Consumers:

- Visualization (Stage 6e, built — its own dedicated branch, not routed
  through the generic Tier 2 registry, since it predates it)
- Future annotated-frame consumers via `Tier2FrameConsumer.on_annotated_frame`
  — no consumer registered today

## Stage 6e: Visualization — AI Streaming (built)

**This is the AI Streaming subsystem, not Live Streaming — do not merge
them.** Live Streaming (Stage 3a) is the always-available raw feed; AI
Streaming is the annotated feed, available only while a camera is
AI-enabled, since it depends on PGIE/Tracker/SGIE having run.

Purpose:

Operator-visible annotated video output. Renders directly from this
pipeline's own inference results — no second inference pass, no OpenCV, no
duplicate metadata extraction.

Component:

`apps/deepstream/app/visualization/` — `VisualizationManager` (sole external
boundary), `VisualizationPipelineBuilder`, `DeepStreamOverlayRenderer`,
`RtspStreamServer`.

Fork point:

Its own `tee` immediately after Secondary GIE — a sibling of Tier 2's
`nvstreamdemux` fork off the same point, not routed through it. Exists only
when `configs/visualization.yaml`'s `enabled: true`; absent otherwise
(byte-for-byte identical to the pre-visualization pipeline).

Chain:

`tee → queue("viz-queue", leaky, bounded) → nvvideoconvert →
capsfilter(RGBA) → [annotate probe] → nvdsosd → nvvideoconvert →
capsfilter(NV12) → nvv4l2h264enc(iframeinterval=output_fps) → h264parse →
rtph264pay(config-interval=1) → udpsink → RtspStreamServer (RTSP proxy)`.

Metadata immutability:

The annotate probe may write only `rect_params`/`text_params`/new
`NvDsDisplayMeta` — never a detection/classification/tracking field. Strictly
read-only with respect to inference metadata.

Failure isolation:

Any construction/start failure is caught, logged, and converted into
`VisualizationManager.health()` reporting `running=False, reason=<...>` —
inference is never affected.

Output:

RTSP, `rtsp://<host>:<rtsp_port>/<stream_name>`.

---

# Stage 7: Recording ⚠ designed, not implemented

Purpose:

Continuous evidence recording, independent of AI and of Live Streaming.

Frame Source:

Tier 0 (Stage 3) — encoded, not Tier 1 — matching NVIDIA's own Smart Video
Record pattern ("expects encoded frames") and avoiding a redundant
decode+re-encode cycle that consuming Tier 1's raw frames would require.

Consumer:

A new adapter implementing a new `Tier0FrameConsumer.on_encoded_frame`
protocol, mirroring `Tier1FrameConsumer`/`Tier2FrameConsumer`'s existing
shape.

Data type:

Raw compressed H.264 byte segments (not yet muxed into a container).

The one genuinely new design problem — not just "register a consumer":

`services/recording`'s `create_event_clip()` (RM-08, already implemented)
documents a 10s-pre/20s-post buffer policy but has never implemented the
*pre*-incident half — it takes one already-assembled `video_data: bytes`
blob. Something must continuously retain a rolling ~10s window of encoded
frames per camera (a bounded ring buffer) so that when `IncidentCreatedEvent`
fires, the preceding window is actually available.

Open discrepancy, not decided here:

This document's codec (below) says H.265; cameras ingest H.264 (Stage 1) and
`services/recording`'s actual code has no transcode logic — it writes
whatever bytes it receives as-is. Tier 0 passthrough (recommended — cheapest,
matches what's built, matches NVIDIA's pattern) means recordings stay
H.264-in-container. Transcoding to H.265 is a separate, real architectural
decision (adds a decode+encode pass) requiring its own approval.

Recording Mode: Continuous Recording · Codec: H.265 (see discrepancy above)
· Retention: 30 Days (ADR-017, configurable) · Clip Policy: Pre-event buffer
+ Post-event buffer · Generated Events: `ClipCreatedEvent`.

---

# Stage 8: Snapshot ⚠ designed, not implemented

Purpose:

Generate evidence snapshot images, independently of Recording.

Frame Source:

Tier 1 (Stage 5) — raw decoded frames, not Tier 0 — because a snapshot must
become a viewable still image; Tier 1's already-decoded pixels feed a JPEG
encoder directly with no extra decode step, unlike Recording which wants to
avoid decode entirely.

Consumer:

A new adapter implementing the existing `Tier1FrameConsumer.on_raw_frame`.

Data type:

One JPEG byte blob per snapshot (e.g. via `nvjpegenc`, staying GPU-side —
avoids introducing OpenCV/PIL as a new production dependency, consistent
with the existing "Prohibited: OpenCV Production Pipelines" constraint).

Lifetime:

Ephemeral, request-scoped — captured once at/near incident creation, no
rolling buffer.

Generated Events: `SnapshotCreatedEvent`.

---

# Stage 9: Other

Purpose:

Architectural expansion point for future analytics, exporters, integrations,
metadata consumers, forensic modules, etc. — any future
`Tier1FrameConsumer`/`Tier2FrameConsumer`/`Tier0FrameConsumer` registration.

Status:

No consumer today. Do not remove this branch merely because it is unused.

---

# Operator Experience: AI Enable / Disable (built)

Camera Management provides an inline AI Enable/Disable control for every
camera, backed by Camera Runtime v1's existing production components:

- `ai_enabled` is persisted on the Camera Registry (database) in response to
  an explicit operator action.
- Desired State Synchronizer detects the change and dispatches
  `enable_ai`/`disable_ai` to `RuntimeSupervisor`.
- `RuntimeSupervisor` mutates the AI valve — the only component permitted
  to.
- Tier 1 (and once built, Live Streaming) are never affected in either
  direction, by construction (Stage 5's tee sits upstream of the valve).

No process restart, no page refresh, no browser reconnect required.

---

# Event Bus

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

# API Service

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

# Frontend

Repository:

`frontend/` (in-repo since RM-13's `git subtree` consolidation)

Consumes:

- REST APIs
- WebSocket Events
- Live Streaming / AI Streaming (per camera, per Operator Experience above)

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

Generate: `CameraDisconnectedEvent`

## Model Failure

Generate: SystemEvent · Severity: ERROR

## Calibration Failure

Generate: SystemEvent · Severity: ERROR

## Event Bus Failure

Generate: SystemEvent · Severity: CRITICAL

## Publisher / Visualization Failure (built)

A Tier 1/Tier 2 consumer's own failure is isolated per-consumer by
`ConsumerRegistry.dispatch` and must never propagate into the pipeline.
Visualization failures are isolated the same way via
`VisualizationManager.health()`. Neither can take inference down with it.

---

# Performance Targets

Camera Count: 20 · Processing: Real-Time · Deployment: Jetson AGX Orin 32GB
· Architecture: Air-Gapped, Offline-First

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
- Decode, re-encode, or CUDA processing on the Live Streaming path (Stage 3a)

Note on Live Streaming's depay→pay step (Stage 3a): re-framing the same
compressed bytes into a new RTP session (required because RTSP's and
WebRTC's RTP sessions are structurally independent) is not decode/re-encode
and does not violate the constraint above.

Note on transport: WebRTC is Live Streaming's and AI Streaming's current
transport. The architectural subsystems are "Live Streaming" / "AI
Streaming"; the transport underneath may change (e.g. WHIP) without this
document changing.
