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

Amended by ADR-030:

"Backend-controlled video delivery" is reconciled with the single AI-annotated-only WebRTC mechanism: the backend (DeepStream) is the sole producer and controller of what the browser receives. No amendment to the WebSocket-metadata half of this strategy.

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

Amended by ADR-029:

Trigger Source becomes Alert Service (Phase 6), not Threat Engine directly -- Hardware Action Service (Phase 7) is the sole consumer of these Supported Targets. Supported Targets unchanged.

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

Amended by ADR-029:

This eligibility rule is unchanged; it now belongs to Alert Service (Phase 6), not an undifferentiated "Alarm Service." Alert Service produces `AlertRaisedEvent`; Hardware Action Service (Phase 7) is the one that actually triggers hardware per ADR-012.

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

Amended by ADR-030:

The process-separation and dual-channel (Live View + AI Streaming) decision for *video delivery* is superseded. Camera Ingestion's one-upstream-connection-per-camera ownership, and the operational constraint requiring it, are unchanged and remain in force.

Amended by ADR-031:

The `webrtcbin`/signaling transport mechanism described here is replaced by HLS. DeepStream remaining the sole owner/producer of browser-facing video (this ADR's core decision) is unchanged.

---

# ADR-029

Decision:

Post-Media-Architecture-Reset Pipeline Decomposition -- AI Runtime, Production EventBus, Incident Service, Alert Service, Hardware Action Service, and Evidence Service become independent, event-connected subsystems.

Status:

ACCEPTED

Supersedes:

The Design note (RM-11, Phase 2) entry in `docs/IMPLEMENTATION_STATUS.md`, to the extent it made `ThreatEngineRuntimeAdapter` (inside `apps/deepstream`) the orchestrator that calls `CalibrationService.estimate()` -> `ThreatEngine.ingest()` -> `IncidentService.handle_escalation()` -> `AlarmService.trigger()` in-process. That design was explicitly approved and hardware-validated at the time; this ADR replaces it, it does not retroactively invalidate the validation.

Amends:

ADR-012 (Alarm Integration Protocol) -- "Trigger Source: Threat Engine" becomes "Trigger Source: Alert Service." ADR-026 (Alarm Trigger Policy) -- the HIGH/FIRE eligibility rule itself does not change, only its owning service (relocates from an undifferentiated "Alarm Service" to Alert Service).

Problem:

ADR-028 (Media Architecture Reset) proved that folding unrelated subsystems into one OS process couples their failure and startup behavior by construction. Camera Ingestion and Live Streaming were pulled out first because they were the subsystems already causing a measured production defect. The same coupling exists one layer further in: `apps/deepstream` currently also hosts Distance Estimation, Threat Engine evaluation, Incident Service orchestration, and Alarm triggering, all as in-process calls made from inside the AI pipeline's own runtime adapter. This makes DeepStream's process boundary meaningless as a failure/ownership boundary -- a bug or slowdown in incident persistence or alarm hardware can now affect the AI pipeline that has no data dependency on it, the same class of problem ADR-028 already fixed once for camera connectivity.

Separately, the original roadmap's next step (migrating Recording to Camera Ingestion, ADR-028's own Phase 3) is deprioritized: the system's mission-critical path is detection -> incident -> alert -> physical response, not recording. Recording is deferred, not cancelled -- it resumes after Phase 8, unchanged in design (ADR-017, `docs/RECORDING_POLICY.md`).

Decision:

Continue past ADR-028 Phase 2 (Live Streaming) with a new phase sequence, each phase an independent service connected only by events:

- **Phase 3 -- AI Runtime**: `apps/deepstream` is restricted to pure CV-engine responsibilities: subscribe to Camera Ingestion's republished stream, NVDEC decode, `nvstreammux`, Primary GIE, NvDCF tracker, Secondary GIE, custom analytics, metadata extraction (the existing `RuntimeAdapter` boundary, ADR-027), AI OSD, AI Streaming output (unchanged, ADR-028 Stage 5.5). Explicitly prohibited inside `apps/deepstream`: incident logic, alert logic, snapshot logic, database writes beyond existing telemetry, GPIO/siren/floodlight control, notification logic, and any other business rule. Its only outputs are the AI Stream and `ObservationEvent` (see `docs/EVENT_CONTRACTS.md`), carrying what `ThreatEngineRuntimeAdapter` used to consume in-process, built from the existing `FrameObservation`/`DetectionObservation`/`TrackObservation` domain objects (ADR-027) -- serialized onto the bus instead of passed as Python objects. `ThreatEngineRuntimeAdapter`'s orchestration role is removed from `apps/deepstream` under this decision.
- **Phase 4 -- Production EventBus**: RM-04 already built `EventBus` as an abstract contract with `InProcessEventBus` as an explicitly swappable initial implementation (see `docs/IMPLEMENTATION_STATUS.md`'s Design note (RM-04)). Phase 4 is that swap: a real cross-process transport, since Camera Ingestion, Live Streaming, AI Runtime, and every service below now run as independent processes. Zero business logic, typed and versioned per `EVENT_CONTRACTS.md`, reusable outside this project. The concrete transport remains an implementation-time engineering choice, not an architecture decision (same standing note as RM-04); it must remain air-gapped/offline-friendly, no cloud dependency (CLAUDE.md's Offline First principle).
- **Phase 5 -- Incident Service**: consumes `ObservationEvent`. Owns Distance Estimation (calls `services/calibration`, unchanged) and Threat Engine evaluation (calls `services/threat_engine`, unchanged rule table per ADR-015) as part of its own event-handling path, plus incident state machine, lifecycle, evidence association, and persistence (unchanged from RM-07/ADR-021/ADR-024/ADR-025). `ThreatAssessmentEvent`'s logical producer is still "Threat Engine" (the rule table itself does not move or change); it now executes inside the Incident Service process rather than inside DeepStream.
- **Phase 6 -- Alert Service** (new subsystem): consumes Incident events (`IncidentCreatedEvent`/`IncidentUpdatedEvent`). Owns alert generation, severity, deduplication, escalation, and operator notification (UI/SMS/Email/WhatsApp -- partially resolves `docs/OPEN_QUESTIONS.md` Q-005). Owns the HIGH/FIRE alarm-eligibility rule relocated from ADR-026's undifferentiated "Alarm Service." Produces a new `AlertRaisedEvent`.
- **Phase 7 -- Hardware Action Service** (new subsystem): consumes `AlertRaisedEvent`. Owns physical actuation only -- GPIO relay, siren, floodlight, PTZ preset, future physical integrations (ADR-012's Supported Targets, unchanged) -- and nothing else. ADR-012's Trigger Source becomes Alert Service, not Threat Engine.
- **Phase 8 -- Snapshot/Evidence Service** (new subsystem): consumes `ObservationEvent` directly (not gated on Recording or Incident state). Owns full-frame snapshots, object/person crops (new capability -- today's `SnapshotCreatedEvent` is incident-level only), evidence storage, and incident attachment. Splits this scope out of `services/recording`, which today produces both `SnapshotCreatedEvent` and `ClipCreatedEvent`. Event clips (video) remain bundled with the postponed Recording Service; only snapshots/crops move to Phase 8. Evidence Service does not receive frames from AI Runtime directly and AI Runtime does not gain any JPEG/image-writing responsibility -- when a full frame is actually needed, Evidence Service requests it from the already-published AI Streaming output (Stage 5.5, the same representation Live Streaming already subscribes to), per ADR-028's "every media representation exists exactly once": `ObservationEvent → Evidence Service (decides a snapshot is warranted) → requests/captures a frame from AI Streaming → writes the JPEG`. Evidence storage schema (e.g. crop coordinates, parent references) is Phase 8's own design-review-level detail, not decided by this ADR.
- **Phase 9+ -- Recording, Archive, Playback, Search, Export**: postponed, not cancelled -- resumes once Phase 8 is complete. Design unchanged (ADR-017, ADR-028 principle 9, `docs/RECORDING_POLICY.md`).

This sequence (Phase 3 → 4 → 5 → 6 → 7 → 8 → 9+) is locked. It does not change again unless implementation reveals a fundamental architectural issue -- in which case, per the Process Note below, this ADR is amended first, before code changes.

Governing Principles (binding on every phase above):

1. **Observations, not decisions.** AI Runtime's `ObservationEvent` carries only what was directly observed or measured: detections, tracks, classifications, confidence, bounding boxes, timestamps, `camera_id`, `frame_id`. It never carries a decision: no threat level, alert, incident, "intruder," escalation, or "hostile" field. Every decision (threat level, incident, alert, hardware action) is computed downstream, by the service that owns that decision -- never inferred or pre-judged by AI Runtime.
2. **One subsystem, one business capability, communication only through events.** Every independently-deployed subsystem (Camera Ingestion, Live Streaming, AI Runtime, Incident Service, Alert Service, Hardware Action Service, Evidence Service, Recording) owns exactly one business capability. No subsystem may call another independently-deployed subsystem's internal logic directly (e.g. `IncidentService -> AlertService.trigger()` in-process is prohibited) -- only the EventBus connects them. This does not restrict a subsystem's own in-process use of a shared library it is the sole caller of: Incident Service invoking `services/threat_engine`/`services/calibration` (Phase 5, above) is a library call within one process's own boundary, not a cross-subsystem call, and remains permitted exactly as designed.
3. **The EventBus is transport only.** Publish, subscribe, deliver -- nothing else. No filtering, routing logic, business rules, severity-based retries, transformation, or enrichment inside the bus itself. Any of those belong to whichever service consumes the event, never to the bus.

Reason:

Applying ADR-028's own decoupling principle end-to-end: every subsystem below Camera Ingestion should own exactly one responsibility and communicate only through events, so a failure or slowdown in one (recording, alarm hardware, evidence storage) can never propagate to another that has no data dependency on it -- the same guarantee ADR-028 already established for camera connectivity and live video.

Process Note:

If Phase 3 implementation reveals that this ADR is incorrect or incomplete, stop immediately and amend this ADR first, before writing or changing code. Code is never the source of truth for architecture -- this document is (per `CLAUDE.md`'s Architecture Rules priority order).

---

# ADR-030

Decision:

AI-Annotated-Only Video Output -- reversal of ADR-028's process separation and dual-channel design for video delivery.

Status:

ACCEPTED

Amends:

ADR-011 (Frontend Video Delivery Strategy) -- reconciles "backend-controlled video delivery" with the single AI-annotated-only mechanism below; the WebSocket-metadata half is unchanged.

Supersedes:

ADR-028's decision that Live Streaming (WebRTC delivery to the browser) is a separate process from DeepStream, and that two independent channels ("Live View" raw, "AI Streaming" annotated) exist per camera. `DEEPSTREAM_PIPELINE_SPEC.md` Stage 1.5's two-channel model and its "AI Runtime never runs WebRTC/webrtcbin" statement.

Not superseded:

ADR-028's Camera Ingestion decision -- one real upstream RTSP connection per camera, owned by an independent Camera Ingestion Service, republished locally for subsystems to consume. This was driven by a hardware constraint (the physical camera's low concurrent-RTSP-session tolerance) that is unrelated to whether raw video ever reaches a browser, and remains in force unchanged. `Camera Ingestion -> AI Runtime -> ObservationEvent -> EventBus`, ADR-027's anti-corruption layer, ADR-029's phase sequence, and Incident Service are all unaffected by this ADR.

Context:

ADR-028 fixed a measured production defect: `nvinfer` (PGIE/SGIE) synchronous TensorRT engine deserialization blocked `rtspsrc`/depay inside the same `Gst.Pipeline`'s serial `set_state()` walk (9.18s stall). Camera Ingestion, extracted as its own service, fixed that defect and remains correct. ADR-028 additionally decided, on top of that fix, that video *delivery to the browser* should also become a second independent process with two channels (raw and AI-annotated). In practice this produced two coexisting WebRTC implementations, a live raw/annotated input-selector, and a raw "Live View" channel and service (`apps/live_stream`) that was never wired to any real consumer.

Problem:

Radar Eye is an AI surveillance system, not a generic camera-viewing system. There is no product-level requirement for raw, non-AI video in the browser, independent of or in place of AI-annotated video. Maintaining a raw channel, a second process, and a live A/B video switch for a product capability that does not exist is unnecessary architectural surface, not a safeguard.

Decision:

DeepStream (`apps/deepstream`) is the sole owner and producer of the browser-facing video output. The pipeline is: Camera Ingestion (unchanged) -> DeepStream (NVDEC decode -> `nvstreammux` -> PGIE -> NvDCF tracker -> SGIE -> metadata extraction -> OSD annotation -> H.264 encode) -> `webrtcbin`, delivered through the existing, unchanged `apps.api` proxy contract (`POST /cameras/{camera_id}/webrtc/offer`) to the browser. Only one representation of video exists per camera: AI-annotated. There is no raw/non-AI browser-facing video path, no live AI-on/AI-off video switch, and no second Live Streaming process. `apps/live_stream` is removed. The existing, hardware-proven `webrtcbin` transport mechanics (fresh transport triple per browser connection; `iframeinterval` set on the encoder) are kept unchanged -- this ADR reverses process/channel placement, not the transport technology.

Consequences:

If DeepStream is unavailable, Radar Eye's surveillance video is unavailable. This trade-off is explicitly accepted: an operator with no AI running has no meaningful surveillance product regardless of whether unannotated pixels are visible, so preserving a raw fallback "just in case" provides no real capability and is not worth the process/channel complexity it costs. `webrtcbin` (a GStreamer element) being owned by the one process that already owns GStreamer is also more consistent with ADR-027's anti-corruption-layer intent than splitting GStreamer-adjacent code across two processes.

Reason:

Radar Eye's product scope is AI-annotated video, not generic live camera streaming. Architecture should reflect the product it serves rather than preserve generality for a capability that was never a requirement.

Amended by ADR-031:

The `webrtcbin` transport mechanics referenced in this ADR's Decision are replaced by HLS -- see ADR-031. This ADR's own core decision (DeepStream is the sole owner/producer of browser-facing video; AI-annotated-only; no raw channel) is unchanged.

---

# ADR-031

Decision:

HLS Video Delivery -- replaces `webrtcbin`/WebRTC as the browser-facing video transport; DeepStream's AI pipeline becomes fully persistent and is never mutated by a browser connecting, disconnecting, or refreshing.

Status:

ACCEPTED

Supersedes:

ADR-030's and ADR-028's `webrtcbin`/WebRTC transport mechanics (SDP offer/answer, ICE/DTLS lifecycle, the local signaling server, and the per-browser-connection transport sub-branch rebuilt on every `handle_offer()` call). ADR-030's core decision -- DeepStream is the sole owner/producer of browser-facing video, AI-annotated-only, no raw channel, no second Live Streaming process -- is not superseded; this ADR only changes the wire protocol video is delivered over.

Not superseded:

`Camera Ingestion -> AI Runtime -> ObservationEvent -> EventBus`, ADR-027's anti-corruption layer, ADR-029's phase sequence, and Incident Service are all unaffected by this ADR, same as they were unaffected by ADR-030.

Context:

ADR-030 kept WebRTC (`webrtcbin`) as the browser transport, moving only which process owned it. In production use this repeatedly surfaced as the dominant source of engineering cost and instability in the video path: ICE/SDP renegotiation edge cases, a `webrtcbin` reuse bug requiring a fresh transport triple rebuilt on every single browser (re)connection, backpressure/deadlock failure modes when a browser peer went unresponsive, and a multi-session glass-to-glass latency investigation (see `apps/deepstream/app/live_stream/branch.py`'s git history for the `idrinterval` root-cause fix that came out of it) that, even after fixing a real root cause (IDR cadence), left WebRTC's per-connection lifecycle as an ongoing source of complexity disproportionate to the product's actual latency requirement (a surveillance UI, not a real-time conferencing product).

Problem:

The DeepStream AI pipeline dynamically created and destroyed a WebRTC transport sub-branch (queue, payloader, `webrtcbin`) on every browser connect/reconnect -- a fresh transport triple per `handle_offer()` call, requested/released against a permanent output tee. Every reconnect, browser refresh, or additional viewer touched live GStreamer pipeline state inside the same process running PGIE/tracker/SGIE, and a stuck/unresponsive browser peer's `webrtcbin` internals had a documented, hardware-confirmed path to stall the shared SGIE tee -- i.e., a browser-side problem could, in the wrong conditions, affect AI inference for every camera. This is exactly the kind of coupling ADR-028/ADR-029 already eliminated elsewhere (camera connectivity, subsystem process boundaries); WebRTC's per-connection lifecycle re-introduced an equivalent coupling inside the video-delivery branch itself.

Decision:

Replace `webrtcbin` with `hlssink2` (HTTP Live Streaming) as the AI-annotated branch's output sink. Per camera, DeepStream builds exactly one linear chain once, when the camera is added, and tears it down exactly once, when the camera is removed: SGIE tee -> queue -> `nvvideoconvert` -> `nvdsosd` -> `nvvideoconvert` -> `nvv4l2h264enc` -> `h264parse` -> `hlssink2`, writing rolling `segment*.ts` + `playlist.m3u8` files to a shared output directory (`configs/live_stream.yaml`'s `output_dir`, short segments -- `segment_target_duration_seconds: 2`, `playlist_length: 3` -- for low glass-to-browser latency). No output tee, no per-connection sub-branch, no dynamic pad request/release tied to browser activity: `hlssink2` is a single permanent consumer, structurally identical to writing to a file. `apps.api` serves the same directory directly over authenticated HTTP (`GET /cameras/{camera_id}/hls/playlist.m3u8`, `GET /cameras/{camera_id}/hls/{segment_name}`) -- a file hand-off via a shared directory, not a network proxy to a DeepStream-hosted signaling server. The browser plays it via `hls.js` (not native HLS -- native playback cannot attach the `Authorization` header this API requires). All WebRTC-specific code is removed: `webrtcbin`, the local FastAPI signaling server (`apps/deepstream/app/live_stream/signaling_server.py`), the SDP offer/answer proxy route, the output tee and its per-connection transport sub-branch, and the `POST /cameras/{camera_id}/webrtc/offer` contract.

Consequences:

Glass-to-browser latency is now bounded below by HLS segmenting (roughly `playlist_length * segment_target_duration_seconds`, ~3-6s as configured) rather than WebRTC's sub-second potential -- accepted, since Radar Eye's surveillance product has no sub-second latency requirement and this trades a latency ceiling that was never actually being hit reliably in practice for the complete removal of per-connection pipeline mutation, ICE/DTLS/SDP lifecycle, and the coupling failure mode described above. DeepStream is now provably unaffected by browser activity of any kind -- measured directly (2026-08-16): CPU, RSS, and GPU utilization/memory are indistinguishable between zero and three simultaneous browser viewers, since `hlssink2` has no concept of a connected viewer at all. A DeepStream crash now means the last-written HLS files simply stop updating (playback stalls, does not error) until DeepStream restarts and resumes writing -- consistent with ADR-030's already-accepted trade-off that there is no product requirement to view video with no AI running.

Reason:

A dynamically-mutated, per-connection network transport living inside the same process as AI inference is unnecessary architectural surface and a proven source of coupling and instability for a product with no sub-second-latency requirement. A persistent AI pipeline writing to a stable, protocol-simple output that a separate, already-existing authenticated HTTP layer serves is both simpler and structurally incapable of the failure modes WebRTC's lifecycle introduced.

Amended by ADR-032:

`hlssink2`/HTTP file delivery is replaced by low-latency MPEG-TS over a WebSocket relay -- measured glass-to-glass latency with HLS was ~10s, unacceptable for real-time surveillance. This ADR's core decision (DeepStream is the sole owner/producer of browser-facing video; one persistent output, never mutated by browser activity; AI-annotated-only) is unchanged -- only the specific sink/transport (`hlssink2` + HTTP file serving) is superseded.

---

# ADR-032

Decision:

Low-Latency MPEG-TS Video Delivery -- replaces `hlssink2`/HTTP file serving (ADR-031) as the browser-facing video transport; DeepStream's `tcpserversink` output and the AI pipeline's fully-persistent, viewer-agnostic design (ADR-031's central lesson) are unchanged.

Status:

ACCEPTED

Supersedes:

ADR-031's choice of `hlssink2` (HTTP Live Streaming, file-based segments/playlist) as the sink, and `apps.api`'s corresponding `GET /cameras/{camera_id}/hls/playlist.m3u8` / `GET /cameras/{camera_id}/hls/{segment_name}` file-serving routes. ADR-031's architectural lesson -- DeepStream owns exactly one persistent video output per camera, built once at camera-add and torn down once at camera-remove, never mutated by browser connect/disconnect/viewer-count -- is not superseded; this ADR keeps that design and only changes the sink element and the mechanism `apps.api` uses to reach it.

Not superseded:

`Camera Ingestion -> AI Runtime -> ObservationEvent -> EventBus`, ADR-027's anti-corruption layer, ADR-029's phase sequence, and Incident Service are all unaffected, same as they were unaffected by ADR-030/ADR-031.

Context:

ADR-031 replaced WebRTC with HLS specifically to eliminate per-connection pipeline mutation and its associated instability. That goal was achieved and remains achieved under this ADR. However, real-camera, real-browser measurement of the ADR-031 implementation (2026-08-16, immediately following its own initial validation) found actual glass-to-glass latency of approximately 10 seconds -- an artifact of HLS's segment-based design (a client can only ever be as current as the most recently *completed* segment, and a decodable start requires at least one full segment plus playlist round-trip), not a misconfiguration. This is unacceptable for Radar Eye's real-time military surveillance mission, which requires latency as close to real-time as practically achievable.

Problem:

Radar Eye needed a browser-compatible LAN video transport that is simultaneously: (a) low-latency (sub-second, or as close as practically achievable), (b) capable of serving multiple simultaneous browser viewers, and (c) structurally incapable of requiring DeepStream's AI pipeline to be mutated by browser connect/disconnect (ADR-031's non-negotiable architectural lesson, kept). WebRTC (ADR-030-era) satisfied (a) but violated (c) by design (a per-connection transport sub-branch). HLS (ADR-031) satisfied (c) but failed (a) by roughly an order of magnitude versus the requirement.

Investigation:

The actual GStreamer/DeepStream environment was inspected before choosing (`gst-inspect-1.0`, this GStreamer 1.20.3 build) rather than assumed: `hlssink2`/fragmented `mp4mux` (CMAF-style low-latency fMP4 over a raw byte broadcast) was considered and rejected at the design stage -- fragmented MP4's one-time "moov" initialization segment is emitted once, at pipeline start, and a client (or, here, `apps.api`'s relay) connecting afterward would need that segment re-served or cached out-of-band before it could initialize `MediaSource`, an unproven mechanism on this GStreamer version's `tcpserversink`/`multifdsink`. MPEG-TS was chosen instead specifically because it does not have this problem: `mpegtsmux`'s default `pat-interval`/`pmt-interval` (9000 ticks @ 90kHz = 100ms) repeat the program tables continuously, and combined with the already-tuned ~1s IDR cadence (ADR-030-era `idrinterval` fix), any client connecting at an arbitrary moment can self-initialize within about one GOP -- the same self-describing, join-anytime property broadcast/cable MPEG-TS systems have always relied on. This was validated empirically, not assumed: a minimal end-to-end prototype (real camera, real `nvv4l2h264enc` hardware encoder, real browser) was built and measured before committing to the design.

Decision:

Per camera, DeepStream's OSD/encode chain (unchanged from ADR-031: `SGIE tee -> queue -> nvvideoconvert -> nvdsosd -> nvvideoconvert -> nvv4l2h264enc -> h264parse`) now feeds `mpegtsmux -> tcpserversink` instead of `hlssink2`. `tcpserversink` binds one fixed local TCP port per camera (loopback only) and natively accepts any number of simultaneous TCP client connections -- GStreamer's own built-in multi-client fan-out, not application code -- with `sync-method=next-keyframe` so a newly-connecting client always starts from a clean, decodable point. The branch is still built exactly once at camera-add and torn down exactly once at camera-remove; still no output tee, no per-connection sub-branch, no dynamic pad request/release of any kind. `apps.api` discovers each camera's assigned port via `camera_media_endpoints` (`subsystem="live_stream"`, the same DB-backed service-discovery mechanism `apps.ingestion` already uses for its own RTSP republish endpoint) and exposes one authenticated WebSocket route, `GET /ws/cameras/{camera_id}/video`, that opens one dedicated TCP connection to that port per browser connection and relays bytes verbatim in both directions -- a pure byte relay holding no shared/broadcast state of its own; `tcpserversink` is what makes multiple simultaneous viewers possible, not this route. The browser plays the stream via `mpegts.js` (MIT-licensed, MSE-based, purpose-built for exactly this "raw MPEG-TS over WebSocket, low latency" pattern), replacing `hls.js`. `hlssink2`, the `GET /cameras/{camera_id}/hls/...` routes, and `LiveStreamHttpSettings` are removed.

Consequences:

Measured directly (2026-08-16, real camera, real browser, burned-in wall-clock overlay compared against actual capture-instant wall-clock time): glass-to-glass latency of approximately 0-1.2 seconds across repeated samples -- meeting the sub-second/near-real-time requirement, roughly an order of magnitude improvement over HLS's ~10s. Startup time (page navigation to first decodable frame): ~1.3s. Page reload and three simultaneous browser viewers both verified working with zero DeepStream pipeline-mutation log activity and CPU/RSS/GPU indistinguishable from zero-viewer baseline (same measurement methodology as ADR-031's own validation) -- ADR-031's central architectural property (viewer lifecycle cannot touch the AI pipeline) holds under this transport exactly as it did under HLS. `apps.api` now holds one live TCP relay connection per browser viewer per camera for the connection's duration (bounded by concurrent viewer count, not by AI/GPU load) -- a new but small and well-understood resource, unlike WebRTC's per-connection GStreamer state.

Reason:

Sub-second glass-to-glass latency is a hard requirement for real-time military surveillance and HLS could not meet it by construction, regardless of tuning (confirmed by measurement, not assumed). MPEG-TS over a WebSocket byte relay meets the latency requirement while preserving every structural guarantee ADR-031 established -- DeepStream's AI pipeline remains fully persistent and completely unaware of browser viewer lifecycle -- because the relay and the multi-client fan-out both live entirely outside DeepStream's own process and pipeline graph.

---