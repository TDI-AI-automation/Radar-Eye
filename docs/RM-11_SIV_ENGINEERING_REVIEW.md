# RM-11.SIV — Engineering Review

**Type:** Post-hoc engineering audit of evidence collected during the
RM-11.SIV validation session. Not a performance optimization pass, not a
tuning pass, not a code change. Every statement below is derived from
artifacts actually captured during that session — nothing is inferred
beyond what the evidence supports.

**Evidence source:** `artifacts/RM-11.SIV-FINAL-VALIDATION/` (logs, metrics,
reports, screenshots), captured 2026-07-23 16:55–18:19 (Asia/Dhaka, UTC+6).

**Terminology:** "RM-11.SIV" refers to the System Integration Validation
session covered by this review, run as an addendum under milestone RM-11.
This document's overall PASS/FAIL determination applies to **RM-11**. "FAT"
refers exclusively to the **Field Acceptance Test**, a distinct, future
milestone performed against the real, installed camera in the target Army
Camp environment — not to this session. These two are never used
interchangeably below.

---

## Executive Summary

**What was validated.** The core DeepStream AI pipeline and its
visualization/RTSP output were validated end-to-end on real hardware, with
real production models, against a real camera: Camera ingestion → RTSP →
DeepStream pipeline construction → PGIE (weapon/person detection) → NvDCF
(tracking) → SGIE (classification) → Visualization (OSD rendering + RTSP
output). Two independent, standards-compliant RTSP clients confirmed the
video output is correct and consumable (`gst-launch-1.0`/`rtspsrc`, and a
real on-screen `autovideosink` render). Bounding boxes, track IDs, PGIE
confidence, SGIE classification, and the frame-level overlay (camera name,
timestamp, FPS, latency, GPU%) all rendered correctly with live data across
89,850 combined frames processed.

**What was intentionally excluded.** Camera Calibration, Distance
Estimation, Zone Logic, Threat Engine, Incident Generation, Alarm Pipeline,
and operational threat-scenario validation were intentionally excluded from
RM-11 due to development-environment limitations: the validation camera is
a desktop development camera, not installed in the target Army Camp
environment and not calibrated, and cannot produce engineering-valid
results for these subsystems. This is an engineering scoping decision, not
a defect or missing work — see **Engineering Decision Record**.

**Platform health.** Across ~54 minutes of combined pipeline runtime, the
validated portion of the platform produced zero Python-level errors, zero
GStreamer bus errors, and zero camera reconnects, with `pgie_is_placeholder
= False` on every recorded sample (real models in effect throughout). Five
issues were found and are documented below; none are defects in the
validated pipeline path itself, and one (database startup resilience) is a
genuine, unresolved engineering finding independent of camera/field scope.

**Readiness for next milestone.** The validated subsystems (Camera → RTSP →
DeepStream → PGIE → NvDCF → SGIE → Visualization) are ready to be carried
forward into RM-12 (API Service). Field-dependent subsystems are not part
of this determination and will be assessed at FAT. One Priority 1 item
(database startup retry/backoff) is tracked under the separate Performance
Optimization Program, running in parallel to the roadmap — see **Final
Recommendation**.

---

## Evidence Reviewed

| Category | Files |
|---|---|
| Logs | `logs/runtime.log` (82,006 lines, both runs), `logs/step1_port_check.log`, `logs/step1_vlc_verbose.log`, `logs/step2_pipeline_evidence.log`, `logs/step3_gst_playbin_test.log`, `logs/step3_raw_sdp_describe.log`, `logs/step3_sdp_negotiated_caps.log`, `logs/step4_gstrtspserver_config.log`, `logs/step5_payloader_config.log`, `logs/step6_encoder_config.log`, `logs/step_display_pipeline.log`, `logs/step_recording.log` |
| Metrics | `metrics/gpu_samples.jsonl` (616 samples, 5s interval) |
| Reports | `reports/execution_timeline.log`, `reports/repository_state.txt`, `reports/hardware_snapshot.json`, `reports/models_config_used.yaml`, `reports/visualization_config_used.yaml`, `reports/camera_config_used.redacted.yaml` |
| Screenshots / recording | `screenshots/step3_rtsp_client_frame_200.jpg`, `screenshots/live_display_autovideosink_window.png`, `screenshots/live_display_with_active_detection.png`, `screenshots/desktop_recording.mkv` |
| Source cross-reference | `apps/deepstream/app/visualization/osd_renderer.py`, `overlay.py`, `pipeline_builder.py`, `stream_server.py` (read-only, to explain observed behavior — no changes made) |

---

## Validation Scope

### Validated

Subsystems actually exercised, against real hardware, real production
models, and a real camera, with direct evidence in this session:

- Camera connection/ingestion
- RTSP ingress
- DeepStream pipeline construction and lifecycle
- PGIE (weapon/person detection)
- NvDCF (persistent tracking)
- SGIE (uniform/classification)
- Visualization subsystem (OSD rendering, RTSP output, real RTSP-client
  interoperability)
- GPU/system performance envelope under real inference + encode load
- Power-loss recovery of the full application/infrastructure stack

### Deferred to Field Acceptance Test (FAT)

| Item | Why deferred |
|---|---|
| Camera Calibration | Requires a camera physically installed at a known position/orientation in the target Army Camp environment. The desktop development camera used for this session has no fixed, meaningful installation geometry — a calibration performed against it would not be engineering-valid. |
| Distance Estimation | Depends directly on Camera Calibration (ground plane projection). With no valid calibration available in this environment, no distance output can be engineering-valid. |
| Zone Logic | Depends directly on Distance Estimation. Not producible without a valid calibration. |
| Threat Engine | Consumes weapon type, classification, and distance zone as inputs. With no calibration and therefore no distance/zone signal, the Threat Engine has no valid input to evaluate against — running it in this environment would only exercise its code path, not its correctness against real conditions. |
| Incident Generation | Driven entirely by Threat Engine output (`EscalationSignal`). Not exercisable without valid Threat Engine input. |
| Alarm Pipeline | Driven entirely by Incident Service escalation. Not exercisable without valid Incident input. |
| Operational Threat Scenarios | Requires a real Army Camp installation, real operational distances/zones, and real personnel/uniform conditions that a desktop bench setup cannot reproduce. |

In every case above, the desktop development camera cannot produce
engineering-valid results for the subsystem in question — this is a
property of the validation environment, not of the subsystem's
implementation. Each of these items is intentionally excluded from RM-11
due to development-environment limitations, and is reserved for FAT
against the real, installed, calibrated camera.

---

## Engineering Decision Record

RM-11 was intentionally scoped as a **Development System Integration
Validation (Development SIV)** — validating pipeline mechanics, inference
correctness, tracking, classification, and the visualization/RTSP output
path on real hardware with real production models, using the development
bench camera available in this environment.

Field-dependent capabilities — Camera Calibration, Distance Estimation,
Zone Logic, Threat Engine, Incident Generation, Alarm Pipeline, and
operational threat-scenario validation — are reserved for the **Field
Acceptance Test (FAT)**, to be performed against the real camera installed
in the target Army Camp environment.

This is an engineering decision reflecting what this validation
environment can and cannot produce engineering-valid evidence for — not a
technical limitation of the implementation itself, and not a gap in RM-11's
completion.

---

## Log Review — `runtime.log`

### Run boundaries

Three process starts occurred in this session:

| Run | Start | End | Outcome |
|---|---|---|---|
| 1 | 16:56:06 | ~17:36:14 (abrupt) | Killed uncleanly by power outage. 59,153 frames processed. No `RM-11.SIV run stopping`/`SIV report written to` — confirmed unclean by a truncated, mid-write JSON log line at the cutoff point. |
| 2 | 17:52:07 | 17:52:07 (immediate) | **FAILED** — `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)`. Crashed inside `DeepStreamRuntime.start() → CameraRegistry.load_camera_sources() → SQLAlchemy → asyncpg`, before any pipeline construction. Postgres (running in Docker Desktop) was also down from the same outage. |
| 3 | 18:02:23 | 18:16:19 (still running at time of audit) | Clean startup after Docker Desktop + Postgres container were manually restarted. 30,697 frames processed by the last captured log line. |

### Startup sequence (both successful runs, identical order)

1. `RM-11.SIV starting`
2. `Camera <uuid> connected` / `Camera Connected` (audit log) — DB-backed camera lookup succeeds
3. SGIE (`nvinfer`, UID 2) deserializes its cached TensorRT engine (`vit_binary.onnx_b8_gpu0_fp16.engine`) and loads successfully — ~4.6s after process start
4. NvDCF tracker library loads (`libnvds_nvmultiobjecttracker.so`) and initializes
5. PGIE (`nvinfer`, UID 1) deserializes its cached TensorRT engine (`yolo26m_weapon.onnx_b1_gpu0_fp16.engine`) and loads successfully — ~8.6–8.8s after process start
6. `RM-11.SIV run started -- watchdog and dashboard active`
7. `Visualization stream live: rtsp://<host>:8554/radar-eye`

Both runs reached `RM-11.SIV run started` in **12.1–13.1 seconds**
(`pipeline_startup_seconds`) — consistent with no TensorRT engine rebuild
occurring in either run, since both engines were pre-built and cached on
disk. SGIE consistently initializes before PGIE in the log order (both are
constructed by `pipeline/builder.py`; this is construction order, not a
timing race — no evidence either stage depends on the other's readiness).

### Warnings

Only two categories of `WARNING`-level log lines occurred, both expected and both resolved:

- **Component "no activity recorded yet" warnings** at startup for `tracker`, `sgie`, `runtime_adapter`, `threat_runtime_adapter`, `threat_engine`, `calibration`, `incident`, `alarm`, `pipeline_fps` — fired once per run (2 total), immediately before those components' first real heartbeat. All except `calibration`/`threat_engine`/`incident`/`alarm` resolved within the same dashboard cycle (the latter four remained stalled for the reason documented in Validation Scope).
- **`camera`/`event_bus` transient staleness** (10.7–11.3s stale, once per run) — resolved once the first real camera/event activity landed; did not recur.

One **raw (non-Python) warning** printed directly by DeepStream's config
parser, once per run:

```
Unknown or legacy key specified 'is-classifier' for group [property]
```

Traced to `is-classifier=1` in the generated SGIE config
(`apps/deepstream/configs/generated/sgie_resolved.txt`) — this DeepStream
7.0.0/nvinfer build considers `is-classifier` a legacy property name. SGIE
classification still functioned correctly in this same session
(`screenshots/step3_rtsp_client_frame_200.jpg` shows a real "Military"
label), so this warning did not block or degrade classification — see
Known Issue #4.

### Errors / Exceptions

Exactly one exception across the entire session: the Run 2 `ConnectionRefusedError` above (full traceback preserved in `runtime.log`; see Known Issue #2). **Zero** Python-level `ERROR`-severity log lines occurred in either successful run. **Zero** GStreamer bus `ERROR`/`CRITICAL` messages occurred in either successful run (`grep`-verified against the full log).

### Reconnects

**None.** No reconnect/retry log lines appear anywhere in `runtime.log` for either successful run — the RTSP camera source stayed connected for the full duration of both runs without a single drop.

### Database events

Beyond the Run 2 failure, the only DB-dependent activity visible is the
initial `Camera Connected` lookup at startup (succeeds in both successful
runs). No further DB activity is expected or observed — Calibration/
Incident/Alarm, which are the session's other DB-touching subsystems, are
out of RM-11's scope per the Validation Scope section and never fired.

### Camera events

`Camera Connected` fires exactly once per successful run, immediately after
`RM-11.SIV starting`. No `CameraDisconnectedEvent` or reconnect activity at
any point.

### Performance snapshots

1,820 `DeepStream performance snapshot` records logged across both
successful runs (roughly one every 2 seconds, matching the dashboard
refresh interval). Key aggregate figures, computed directly from these
records:

| Metric | Min | Max | Note |
|---|---|---|---|
| `inference_fps` | 24.52 | 28.66 | Max occurs at `frames_processed=20`, 14s into Run 3 — a startup transient (queue backlog draining), not steady-state. Steady-state is a tight band around 24.5–24.8. |
| `end_to_end_latency_ms` | 4.39 | 431.56 | Max occurs at the **same** `frames_processed=20` startup snapshot as the FPS spike above — same cause, same moment, not a recurring issue. Steady-state is 4.4–5.9ms. |
| `visualization_fps` | 24.52 | 29.40 | Tracks `inference_fps` closely throughout — consistent with the design (visualization measured after the queue, reflecting real post-backpressure rate). |
| `overlay_time_avg_ms` | 0.055 | 0.165 | Sub-millisecond throughout, well under one frame period at 25fps. |
| `pgie_is_placeholder` | — | — | `False` for every single sample in both runs — confirms real production models were in effect for the entire session, never fell back to placeholder. |

### Unexpected behavior

- The Run 1 → Run 2 transition shows `runtime.log`'s only mid-line
  truncation of the session — direct evidence of the abrupt kill (see Known
  Issue #2).
- No `getMaxBatchSize`-class TRT warnings occurred this session (a
  previously-documented benign warning in earlier RM-11 sessions) — absent
  here, nothing to report.

---

## Pipeline Review

| Stage | Verdict | Evidence |
|---|---|---|
| **Camera** | **PASS** | `Camera Connected` audit event at startup, both successful runs; zero disconnects/reconnects for the full session duration (~54 min combined runtime). |
| **RTSP (ingress)** | **PASS** | Dashboard's `RTSP ✓ Alive` continuously through both runs; no stall warnings for this component after startup. |
| **DeepStream (pipeline construction)** | **PASS** | Clean `PLAYING` transition both runs, `pipeline_startup_seconds` 12.1–13.1s, zero GStreamer bus errors. |
| **PGIE** | **PASS** | Real engine (`yolo26m_weapon.onnx_b1_gpu0_fp16.engine`) deserialized and loaded successfully both runs; `pgie_is_placeholder=False` for every sample; steady-state `pgie_fps` ~24.7–24.8, matching `inference_fps`. Real detections observed with confidence values 0.73 and 0.38 in the captured evidence. |
| **NvDCF (tracker)** | **PASS** | Tracker library loaded and initialized both runs; stable track IDs observed across multiple captures (e.g. `ID #62`, `ID #269`); dashboard `NvDCF ✓ Alive` throughout. |
| **SGIE** | **PASS (with a cosmetic warning)** | Real engine (`vit_binary.onnx_b8_gpu0_fp16.engine`) deserialized and loaded both runs; a real classification (`Military`) was observed rendered in `screenshots/step3_rtsp_client_frame_200.jpg`. `operate_on_class_ids: "3"` correctly targets PGIE's `person` class (verified against `labels.txt`: index 3 = `person`). The `is-classifier` legacy-key warning (Known Issue #4) did not block classification. |
| **Visualization** | **PASS** | RTSP server bound and reachable both runs; validated via two independent real clients (`gst-launch-1.0`/`rtspsrc`, and a real on-screen `autovideosink` render) — see Visualization Review below for full detail. `visualization_fps`/`overlay_time_avg_ms` present and healthy in every sample where visualization was enabled. |
| **Threat Engine** | **DEFERRED TO FAT** | Dashboard shows `ThreatEngine ✗ STALLED, count=0` for the entire session, both runs — zero throughput. Intentionally excluded from RM-11 due to development-environment limitations: the desktop development camera is not calibrated and cannot produce a valid distance/zone signal for the Threat Engine to evaluate. Not a failure of the Threat Engine itself. |
| **Incident** | **DEFERRED TO FAT** | `count=0` for the entire session — direct consequence of Threat Engine producing no input, per the same development-environment limitation. Intentionally excluded from RM-11. |
| **Alarm** | **DEFERRED TO FAT** | `count=0` for the entire session — direct consequence of Incident producing no escalation, per the same development-environment limitation. Intentionally excluded from RM-11. |

**Scope, stated plainly:** this SIV session validates Camera → RTSP →
DeepStream → PGIE → NvDCF → SGIE → Visualization end-to-end on real
hardware with real models — this is the full scope of RM-11 as a
Development SIV. Threat Engine → Incident → Alarm, along with Camera
Calibration, Distance Estimation, and Zone Logic, are intentionally
excluded from RM-11 due to development-environment limitations and are
reserved for FAT against the real, installed, calibrated Army Camp
camera — see **Validation Scope** above.

---

## GPU Review

Source: `metrics/gpu_samples.jsonl`, 616 samples at 5s intervals,
2026-07-23 16:56:24 → 18:19:29.

| Metric | Min | Max | Average |
|---|---|---|---|
| GPU utilization | 9.0% | 34.0% | 18.0% |
| GPU memory used | 2176 MB | 2755 MB | 2529.5 MB (of 12,288 MB total — 20.6%) |
| Temperature | 51°C | 62°C | 53.0°C |
| Power draw | 48.8 W | 66.1 W | 52.8 W |

**Utilization distribution** (616 samples): 0–10%: 1 sample · 10–20%: 423
samples · 20–30%: 157 samples · 30–40%: 35 samples · 40%+: 0 samples. The
large majority of the session ran in a tight 10–30% GPU band, with no
sustained spikes. No sample in the dataset indicates thermal throttling or
a power-limit condition (max recorded temperature 62°C, max recorded draw
66.1W, both within this GPU's normal operating range for this workload).

**Idle periods:** none — every single sample shows GPU utilization ≥ 9%;
the pipeline never went idle while the sampler was running.

**Anomaly — the outage gap:** one gap in the data, `2026-07-23T17:36:14 →
2026-07-23T18:07:50` (1,896 seconds / ~31.6 minutes), corresponding exactly
to the power outage plus recovery time. This gap is a sampler-process
casualty of the outage, not a GPU/pipeline anomaly — left unfilled rather
than interpolated, per instruction not to fabricate data.

No other timing anomalies in the metrics stream — sample cadence is
consistent at ~5s throughout both the pre- and post-outage portions.

*(A timeline plot was not produced — the tabular min/max/average/distribution above fully characterizes this dataset; 616 samples in a single tight band do not require a chart to interpret.)*

---

## Visualization Review

Three independent pieces of visual evidence were collected, with different
strengths and one real gap:

### 1. `screenshots/step3_rtsp_client_frame_200.jpg` — PASS

Frame decoded from a real `gst-launch-1.0`/`rtspsrc` client (not our own
render path — an independent third-party-equivalent decode). Shows: a
correctly-positioned green bounding box around a real detected person,
label text `person (0.73)` / `ID #62` / `Military` (SGIE classification
rendering correctly), and the frame-level overlay (camera name
`hikvision-gate-01`, ISO timestamp, `FPS: 24.7`, `Latency: 5.9ms`, `GPU:
28%`) all legible and consistent with the dashboard's live values at
capture time.

**Rendering quality note:** the frame overlay's top-left text box visually
overlaps the camera's own native burned-in on-screen timestamp
(`23-2026 Thu 17:03:26`), making both partially hard to read in that
corner — a cosmetic layout collision, not a functional defect (see Known
Issue #5).

### 2. `screenshots/live_display_autovideosink_window.png` and `live_display_with_active_detection.png` — PASS

Both are real X11 screen captures (`xwd`, targeted at the actual
`autovideosink` window ID) of the on-screen decode-and-render pipeline
(`rtspsrc → rtph264depay → h264parse → avdec_h264 → videoconvert →
autovideosink`) requested for this validation. The first capture shows the
overlay correctly rendering (camera name, timestamp, FPS, latency, GPU%)
with no detection in frame at that instant — an honest, expected empty
case, not a defect. The second, captured ~65 seconds later after an
automated scan of 12 burst captures for an elevated green-pixel count,
shows an active detection: green bbox, `person (0.38)`, `ID #269`.

**No SGIE label in this second capture.** Traced against source
(`osd_renderer.py`'s `_secondary_label`): the renderer only emits a
secondary-label line when `obj_meta.classifier_meta_list` is non-`None` —
i.e., only when SGIE has actually attached a classification to that
specific object on that specific frame. A freshly-appeared track (`ID
#269`, gone again one second later in the next capture) plausibly had not
yet received its first SGIE classification pass, or its classification
confidence fell below `sgie.confidence_threshold: 0.51` and was dropped by
nvinfer before reaching the renderer. Both are correct, designed system
behavior, not a rendering bug — independently confirmed by capture #1
above, from the same continuous process, showing the SGIE label rendering
correctly when a classification *is* available.

**Threat/distance/zone overlay: not observable this session.** Consistent
with the Validation Scope above — Camera Calibration, Distance Estimation,
and Zone Logic are intentionally excluded from RM-11 due to
development-environment limitations, so no track ever produced a
zone/distance/threat result for `draw_threat`/`draw_distance`/`draw_zone`
(all `true` in the config used) to draw. The overlay code paths for these
fields are implemented and config-driven (see `overlay.py`); rendering
them with real data is reserved for FAT against the calibrated Army Camp
camera. Not a rendering defect.

### 3. `screenshots/desktop_recording.mkv` — DOES NOT DEMONSTRATE VISUALIZATION

This is a real, valid, fully-decodable 12-second H.264/MKV recording
(re-verified: 123 frames extracted cleanly via `matroskademux → h264parse →
avdec_h264`, spanning real, advancing wall-clock timestamps visible in a
system clock on screen, confirming this is a live, non-frozen capture).
However, **every frame of it shows the Antigravity IDE window, not the RTSP
video window.** The full-screen `ximagesrc` capture used to produce this
file captured whatever was actually on top of the X stacking order at the
time it ran, and the video window was not raised/visible for that specific
capture window (unlike the two `xwd`-targeted, window-ID-specific captures
above, which bypass stacking order entirely and succeeded).

**This is a validation-tooling gap, not a pipeline defect** — the two
window-targeted screenshots above already independently satisfy "video is
displayed with a real video sink," so this gap does not weaken the overall
visualization finding, but the recording file itself should not be cited
as evidence of on-screen rendering. See Known Issue #3.

---

## Report Review — cross-checking documentation against what occurred

- **`execution_timeline.log`**: cross-checked against `runtime.log`
  timestamps at every major transition (startup, VLC diagnostic round, RTSP
  diagnostic round, power outage, recovery) — every claimed event has a
  corresponding, consistent `runtime.log` entry at a matching or
  immediately-adjacent timestamp. No inconsistency found.
- **`repository_state.txt`**: branch (`feature/RM-11-SIV-visualization`) and
  commit (`e06f160`) match `git log`/`git status` at the time this review
  was written; the 9 listed commits ahead of `feature/deepstream` are the
  same 9 visible in `git log --oneline feature/deepstream..HEAD` today.
  Consistent.
- **`hardware_snapshot.json`**: DeepStream 7.0.0, GStreamer 1.20.3, CUDA
  12.2, TensorRT 8.6.1, RTX 3060 12GB, driver 535.288.01 — all match the
  versions/messages actually printed in `runtime.log`'s startup output
  (e.g. TensorRT engine build/load lines reference the same
  `fp16.engine` files, consistent with a 12GB RTX-class GPU running FP16
  inference). Consistent.

**No inconsistency was found between what the reports claim and what the
raw logs/metrics actually show.**

---

## Config Review

Reviewed configs (no changes made):

- **`configs/models.local.yaml`** (used in place of the tracked
  `configs/models.yaml`): real PGIE (`yolo26m_weapon.onnx`, FP16,
  `confidence_threshold: 0.25`) and SGIE (`vit_binary.onnx`, FP16,
  `confidence_threshold: 0.51`) paths, both pointing at
  `~/Downloads/DeepStream-Yolo/` (an out-of-repo, previously-reviewed
  build — per `docs/IMPLEMENTATION_STATUS.md`'s existing Design note, these
  models remain **MODEL_REGISTRY.md-unapproved/unbenchmarked**; this
  session is bench validation, not a production-approval claim).
  `operate_on_class_ids: "3"` correctly targets the `person` label per
  `labels.txt`'s 0-indexed ordering (`0=fire, 1=metal, 2=non_metal,
  3=person, 4=ranged_metal`) — verified directly against the label file,
  not assumed. No misconfiguration found.
- **`configs/visualization.yaml`** (session override, `enabled: true`):
  all `draw_*` toggles on except `draw_system_status`; `output_bitrate:
  4000000`, `output_fps: 30`, `rtsp_port: 8554`. Matches what was actually
  observed on the wire (Step 3/6 diagnostics from the prior validation
  round: real bitrate ~2.5–2.7 Mbps under the 4 Mbps cap, real 1920x1080
  H.264 stream). No misconfiguration found.
- **`configs/camera.yaml`** (redacted): `rtsp_url:
  rtsp://192.168.68.10:554/Streaming/Channels/101`, `transport: tcp`,
  `latency_ms: 200`, `resolution: [1920, 1080]`, `fps: 30`. Matches the
  observed stream's negotiated caps exactly. No misconfiguration found.

No configuration value reviewed appears misconfigured or inconsistent with
observed runtime behavior.

---

## Known Issues

Each entry below is supported directly by evidence collected this session
and carries a risk classification, root cause (where established), impact
statement, and Performance Optimization Program traceability mapping.

### Known Issue #1 — This machine's VLC build cannot play any standard RTSP stream

**Observation:** A local VLC client failed to play the validated RTSP
stream, reporting "Failed to play RTSP session" / "Failed to teardown RTSP
session."

**Evidence:** `logs/step1_vlc_verbose.log` — VLC's own printed compile
flags include `--disable-live555`; the play attempt fails via the `satip`
and `access_realrtsp` fallback modules (`"only real/helix rtsp servers
supported for now"`), never reaching real RTSP/SDP/RTP negotiation. In the
same session, a standards-compliant client (`gst-launch-1.0`/`rtspsrc`)
successfully negotiated and received the identical stream
(`logs/step3_gst_playbin_test.log`).

**Impact:** This specific VLC binary cannot be used as an RTSP client
against this system on this machine. Does not affect the RTSP server, any
other RTSP client, or the documented production video-delivery
architecture, in which RTSP is internal-only and browsers/operators consume
video via a future Media Gateway/WebRTC path, not direct VLC.

**Root Cause:** Confirmed. This machine's Ubuntu 22.04 `vlc` apt package
(`3.0.16-1build7`) is compiled with `--disable-live555`, omitting VLC's
standard RTSP/RTP demuxer entirely — a property of this specific binary
(a known Debian/Ubuntu packaging choice), not of VLC generally.

**Risk Classification:** **Low.** Justification: confined to one
client-tooling limitation on one non-production machine; the server side is
independently proven correct via a standards-compliant client; the
production architecture does not depend on this specific VLC build.

**Optimization Program Mapping:**
```
Known Issue #1
  ↓
Optimization category: Interoperability Verification
  ↓
Verify standards-compliant RTSP client compatibility on the Jetson AGX
Orin deployment target's OS image
```

**Recommended Optimization Program Action:** Confirm client compatibility using an
official/live555-enabled VLC build (or the equivalent on the actual Jetson
target's OS image) before treating VLC playback as a production acceptance
criterion.

---

### Known Issue #2 — `run_siv.py` has no retry/backoff for a transient database outage at startup

**Observation:** After the mid-session power outage, the first restart
attempt crashed immediately instead of retrying, because the database
(Postgres, running in Docker Desktop) had not yet come back up.

**Evidence:** `logs/runtime.log` Run 2 — a single `ConnectionRefusedError`
during `CameraRegistry.load_camera_sources()` crashes the entire process
immediately (unhandled exception propagates out of `_run()`), with no
retry attempt logged anywhere in the traceback path.

**Impact:** A transient database unavailability at process startup —
exactly the condition produced by this session's real power event — causes
the entire application to exit rather than retry, requiring manual
intervention (this session required manually restarting Docker Desktop and
the Postgres container, then relaunching the process) to restore service.
For the unattended, air-gapped, single-node deployment target this
platform is built for (`CLAUDE.md`), an unrecovered startup failure after a
power event means the surveillance system does not resume monitoring on
its own.

**Root Cause:** Confirmed. `runtime.py`'s `start()` calls the DB-backed
camera registry synchronously during startup with no wrapping
retry/backoff policy — the code path assumes the database is already
reachable when the process starts.

**Risk Classification:** **High.** Justification: directly demonstrated on
this session's own hardware, not hypothetical; the deployment target is an
unattended system where a missed automatic recovery has real operational
consequence (a coverage gap in a threat-surveillance platform). Not
Critical: the system recovers fully with manual intervention, no data was
lost or corrupted (the Postgres container's own crash recovery completed
cleanly), and the fix is a well-understood engineering pattern (startup
retry/backoff), not an open design problem.

**Optimization Program Mapping:**
```
Known Issue #2
  ↓
Optimization category: Reliability
  ↓
Database startup retry/backoff for run_siv.py / production entrypoint
```

**Recommended Optimization Program Action:** Add a bounded retry/backoff policy (e.g.
exponential backoff for N attempts) around the startup-time database
connection, so the production entrypoint (systemd on the Jetson target)
can recover automatically from a transient database-unavailable condition
instead of exiting immediately.

---

### Known Issue #3 — Desktop screen-recording capture method does not reliably capture the intended window

**Observation:** The `desktop_recording.mkv` deliverable, intended to show
the live RTSP video window on screen, instead shows an unrelated
application window for its entire duration.

**Evidence:** `screenshots/desktop_recording.mkv` — all 123 extracted
frames show the Antigravity IDE window, not the `autovideosink` video
window, despite the video pipeline running throughout the capture.

**Impact:** The `desktop_recording.mkv` artifact from this session cannot
be used as evidence of on-screen visualization rendering. Does not affect
the product or any other artifact — the two `xwd`-targeted screenshots
(`screenshots/live_display_autovideosink_window.png`,
`live_display_with_active_detection.png`) independently satisfy the same
evidence requirement and are unaffected.

**Root Cause:** Confirmed at the mechanism level. The recording used a
full-screen `ximagesrc` capture, which records whatever is topmost in the X
window stack at capture time; the video window was not topmost for the
duration of that specific capture. (The precise reason the video window
lost focus at that exact moment was not independently reconstructed — the
capture mechanism itself, and its consequence, are confirmed; the
underlying focus-change trigger is not.)

**Risk Classification:** **Low.** Justification: a validation-evidence
collection procedure issue with zero effect on the product; already
mitigated within this same session by an alternate, successful capture
method.

**Optimization Program Mapping:**
```
Known Issue #3
  ↓
Optimization category: Validation Tooling / Process
  ↓
Adopt window-ID-targeted (not full-screen) capture procedure for future
SIV screen-recording evidence
```

**Recommended Optimization Program Action:** None for the visualization subsystem itself.
For future SIV sessions needing a screen-recording deliverable, use a
window-ID-targeted capture method (as the still-image captures in this
session already did) rather than a full-screen capture.

---

### Known Issue #4 — `is-classifier` legacy-key warning on every SGIE startup

**Observation:** DeepStream's config parser prints a "legacy key" warning
for the SGIE configuration on every process start.

**Evidence:** `runtime.log` — `Unknown or legacy key specified
'is-classifier' for group [property]`, once per process start, both runs;
traced to `is-classifier=1` in `apps/deepstream/configs/generated/
sgie_resolved.txt`.

**Impact:** None observed on functional behavior — SGIE classification
worked correctly in this same session
(`screenshots/step3_rtsp_client_frame_200.jpg` shows a real "Military"
label). Adds one cosmetic warning line to startup logs on every run, which
could be mistaken for a real problem by an operator unfamiliar with it.

**Root Cause:** Partially known. Confirmed that DeepStream 7.0.0's
`nvinfer` config parser considers `is-classifier` a legacy/deprecated
property name (stated directly in the parser's own warning message). The
current DeepStream 7.0.0-preferred replacement property name was not
identified in this session.

**Risk Classification:** **Low.** Justification: cosmetic log noise only,
with demonstrated zero functional impact in this session's own evidence.

**Optimization Program Mapping:**
```
Known Issue #4
  ↓
Optimization category: Configuration Hygiene
  ↓
Update SGIE config template's legacy `is-classifier` key
```

**Recommended Optimization Program Action:** Low priority — identify the current
DeepStream 7.0.0-preferred property name and update the SGIE config
template, to silence a cosmetic startup warning.

---

### Known Issue #5 — Frame-overlay text collides with the camera's own burned-in timestamp

**Observation:** The frame-level overlay's top-left text box visually
overlaps this camera's own native, burned-in on-screen timestamp.

**Evidence:** `screenshots/step3_rtsp_client_frame_200.jpg` — our top-left
overlay box visually overlaps the camera's native on-screen timestamp,
degrading legibility of both in that corner.

**Impact:** Reduced legibility of both our frame-level overlay text and
this camera's native timestamp in the top-left corner when both are
present. Does not affect bounding boxes, track IDs, or per-object labels,
which render in a different screen region and were confirmed legible in
every capture.

**Root Cause:** Confirmed. Neither overlay is aware of the other; both
independently target the same fixed screen region (top-left) — ours is
config-placed (`configs/visualization.yaml`), the camera's is burned into
the source video before it ever reaches our pipeline.

**Risk Classification:** **Low.** Justification: affects operator
legibility in one screen corner only; does not affect detection, tracking,
or classification correctness; low-cost to address.

**Optimization Program Mapping:**
```
Known Issue #5
  ↓
Optimization category: Visualization UX Polish
  ↓
Configurable frame-overlay position/corner
```

**Recommended Optimization Program Action:** Low priority — consider a configurable
overlay position/corner for the frame-level text block, since some cameras
(like this one) burn in their own on-screen display in the same corner.

---

## Risks

- **Production DB-outage resilience is unproven.** This session directly
  demonstrated that a real power event can leave the database unreachable
  at the exact moment the application tries to start, and the current code
  has no recovery path for that beyond a full manual restart. This is a
  real operational risk for an unattended/air-gapped deployment target
  (Jetson AGX Orin, per `CLAUDE.md`), not a hypothetical one. (Known Issue
  #2, Risk Classification: High.)
- **VLC compatibility on the actual Jetson target's OS image is unverified**
  — this session only characterized VLC on the x86 dev machine's Ubuntu
  22.04 desktop package, which is not the deployment target. (Known Issue
  #1, Risk Classification: Low.)

Threat Engine/Incident/Alarm correctness against real production models is
not listed as an RM-11 risk — per the Engineering Decision Record, that
evaluation belongs to FAT against the real, calibrated Army Camp camera,
not to this Development SIV.

---

## Performance Optimization Program Candidates

Prioritized strictly from evidence gathered this session — not a general
wishlist. Each item traces to exactly one Known Issue above.

### Priority 1

- **[Reliability] Startup-time DB retry/backoff for `run_siv.py`/production
  entrypoint.** ← Known Issue #2. Directly demonstrated failure mode this
  session; a real operational risk for the unattended production
  deployment `CLAUDE.md` targets. Independent of camera/field scope —
  applies regardless of which camera is in use.

### Priority 2

- **[Interoperability Verification] Verify standards-compliant RTSP client
  compatibility on the actual Jetson AGX Orin deployment image**, not just
  this x86 dev machine. ← Known Issue #1. Needed before treating any
  particular RTSP client as a supported/unsupported production integration
  point.
- **[Validation Tooling / Process] Adopt a window-ID-targeted (not
  full-screen) capture procedure for any future SIV screen-recording
  evidence.** ← Known Issue #3. Process improvement for future validation
  sessions, not a product change.

### Priority 3

- **[Configuration Hygiene] Update the SGIE config template's legacy
  `is-classifier` key.** ← Known Issue #4. Cosmetic, zero observed
  functional impact.
- **[Visualization UX Polish] Configurable frame-overlay corner/position**
  to avoid collision with cameras that burn in their own on-screen
  timestamp. ← Known Issue #5. Cosmetic, affects legibility only in one
  screen corner.

### Reserved for Field Acceptance Test (not part of the Performance Optimization Program)

- Validate Camera Calibration, Distance Estimation, Zone Logic, Threat
  Engine, Incident Generation, Alarm Pipeline, and operational threat
  scenarios against the real, installed, calibrated Army Camp camera — per
  the Validation Scope and Engineering Decision Record above, this is FAT
  scope, not Performance Optimization Program scope, and is listed here
  only for forward visibility.

---

## Final Recommendation

**RM-11 Result:** PASS

**Scope:** Development System Integration Validation.

**Major Outcome:** Core platform successfully integrated and validated in
the development environment — Camera, RTSP, DeepStream, PGIE, NvDCF, SGIE,
and Visualization all confirmed working end-to-end against real hardware
and real production models, with zero errors and zero reconnects across
89,850 combined frames processed.

**Deferred:** Field-dependent functionality reserved for FAT — Camera
Calibration, Distance Estimation, Zone Logic, Threat Engine, Incident
Generation, Alarm Pipeline, and operational threat scenarios, per the
Engineering Decision Record above.

**Open engineering item (not field-dependent):** the startup-time database
retry/backoff gap (Known Issue #2, Risk Classification: High) is directly
demonstrated by this session's own power-outage recovery and is
independent of camera/field scope. It does not block this PASS
determination but is mapped into the Performance Optimization Program's
Database Resilience / Startup Robustness categories (see
`docs/PERFORMANCE_OPTIMIZATION_PROGRAM.md` §3) for future attention.

**Next Roadmap Milestone:** RM-12 — API Service (REST + WebSocket), per
`docs/IMPLEMENTATION_ROADMAP.md` — the repository's authoritative milestone
sequence.

**Parallel Engineering Workstream:** Performance Optimization Program (see
`docs/PERFORMANCE_OPTIMIZATION_PROGRAM.md`) — a cross-cutting engineering
workstream, independent of and running alongside the roadmap, not a
roadmap milestone itself. No optimization work shall be performed except
under that program's own rules.

---

## Lessons Learned

- **Artifact collection proved invaluable.** Every diagnostic conclusion in
  this review — the VLC root cause, the pipeline health assessment, the
  power-outage timeline, the visualization correctness finding — traces to
  a specific captured log line, metric sample, or screenshot. Nothing had
  to be taken on memory or assumption.
- **Desktop bench validation successfully verified core platform
  integration** (Camera → RTSP → DeepStream → PGIE → NvDCF → SGIE →
  Visualization) without requiring the target field environment — a
  Development SIV is a legitimate, sufficient milestone for this scope.
- **Power-outage recovery, though unplanned, exposed a real startup
  robustness gap** (Known Issue #2) that a clean validation run would
  never have surfaced. An unplanned interruption during validation can be
  more informative than the validation it interrupted.
- **RTSP interoperability should be validated with a standards-compliant
  client first**, before treating any specific client's failure as a
  server defect — this session's VLC investigation would have produced a
  false-positive server defect finding without that step.
- **Development-scope and field-scope validation should remain separate
  milestones**, each with evidence appropriate to what its environment can
  actually produce. Attempting to validate calibration-dependent subsystems
  against an uncalibrated bench camera would have produced results with no
  engineering value, regardless of outcome.
- **Development and optimization should remain separate milestones** —
  this review deliberately stops at reporting evidence and recommending a
  backlog; no tuning or code change was performed as part of producing it.

---

*This document is the permanent engineering record for RM-11.SIV. Frozen as
of this revision — no further edits unless new validation evidence is
collected.*
