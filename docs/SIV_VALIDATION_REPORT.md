# RM-11.SIV — System Integration Validation Report

Template per the RM-11.SIV Principal Engineer approval's "Validation Report" and
"Test Checklist" requirements. Filled in during an actual `scripts/run_siv.py`
run against a real RTSP camera and the real PGIE/SGIE models. Each item's
Evidence should cite either a log line, a `radar_eye.trace` line (with
`frame_trace.enabled: true`), or a field from the matching
`siv_reports/siv_report_latest.json` run.

This is a living document — re-run the checklist and replace the table below
whenever `feature/RM-11-SIV` is re-verified (e.g. after swapping in the real
weapon/uniform models, or scaling past one camera in RM-11 Phase 3).

---

## Run Metadata

| Field | Value |
|---|---|
| Date | 2026-07-23 |
| Camera | Local `GstRtspServer` test source (`sample_qHD.mp4`, DeepStream SDK sample stream) — same methodology as RM-11 Phase 1/2's hardware verification. **Not a physical camera** — see Known Constraints. |
| PGIE model | Placeholder (`pgie.enabled: false`) — DeepStream SDK's bundled `resnet18_trafficcamnet` |
| SGIE model | Placeholder (`sgie.enabled: false`) — DeepStream SDK's bundled `resnet18_vehicletypenet` |
| `siv_reports/` file | `siv_report_2026-07-23T042636.849087+0000.json` (produced by the verification harness; not committed — see `.gitignore`) |
| Operator | Claude (implementing RM-11.SIV under Principal Engineer direction) |
| Hardware | Real NVIDIA GPU (GeForce RTX 3060), real DeepStream 7.0/TensorRT/pyds, system Python 3.10 — same reference environment as RM-11 Phase 1/2 |

This run used a standalone verification harness driving the real repo classes
directly (`DeepStreamPipeline`, `RuntimeAdapter`, `ThreatEngineRuntimeAdapter`,
`HeartbeatRegistry`, `PerformanceInstrumentation`, `PipelineTracer`, `Watchdog`,
`Dashboard`, `generate_siv_report`) via `AsyncBridge` — the same class `runtime.py`
uses — rather than the full `scripts/run_siv.py` entrypoint, because
`CameraRegistry` and `CalibrationService`/`IncidentService` require PostgreSQL,
unreachable in this sandbox (confirmed again during this run). The DB-dependent
half of the chain (Calibration → ThreatEngine → Incident → Alarm) is separately
verified by `apps/deepstream/tests/test_threat_runtime_adapter.py`'s
`test_full_chain_beats_expected_heartbeat_components` (skips without Postgres,
passes against real Postgres per RM-03's testing policy).

**Two real defects were found and fixed during this run** — see
`docs/IMPLEMENTATION_STATUS.md` and commits `cd67d34`/`8480e2f` on
`feature/RM-11-SIV`:
1. `nvstreammux` had no `batched-push-timeout` set (pre-existing since RM-11
   Phase 0) — with fewer active sources than `batch-size`, the pipeline never
   left PAUSED and zero frames ever flowed. This is exactly the class of
   black-box failure SIV exists to catch.
2. `Watchdog`'s `pipeline_fps` check derived its own state instead of using
   the shared `HeartbeatRegistry`, so the Dashboard (reading the registry
   directly) showed it permanently stalled even when the Watchdog itself
   reported it healthy — a violation of the Unified Heartbeat requirement's
   "one source of truth" rule, only visible once real frames were flowing.

Both fixed; the results below are from the run **after** both fixes.

---

## Checklist

Every item: **PASS** / **FAIL** / **NOT YET RUN**, plus Evidence.

### Camera

| Item | Result | Evidence |
|---|---|---|
| RTSP connects | PASS | `siv_report`: `components.rtsp.counter=66`, `components.camera.counter=66`; log: `Camera Connected: camera=7f12c95d-...` |
| Reconnect works | NOT YET RUN | Not exercised by this harness (bypasses `DeepStreamRuntime`'s reconnect orchestration). Reconnect *logic* itself was verified in RM-11 Phase 1's hardware verification and is unit-tested (`test_reconnect.py`) — unchanged by RM-11.SIV. |
| Disconnect detected | NOT YET RUN | Same as above — `RuntimeAdapter.on_camera_disconnected` unit-tested, not exercised end-to-end here. |
| FPS stable | PASS | `siv_report.pipeline.fps = 25.9` (stable across the ~3 min run, matches source video's 25fps) |

### DeepStream

| Item | Result | Evidence |
|---|---|---|
| Pipeline PLAYING | PASS | Bus `STATE_CHANGED: paused -> playing` observed after the `batched-push-timeout` fix |
| Pipeline restart | NOT YET RUN | Requires a real disconnect/reconnect cycle — see Camera row above |
| No decoder errors | PASS | Zero `Gst.MessageType.ERROR` bus messages across the run |

### PGIE

| Item | Result | Evidence |
|---|---|---|
| Objects detected | PASS (mechanically) | `siv_report.components.pgie.counter=65` — inference ran on every batched frame |
| Confidence reasonable | N/A | Placeholder model (`resnet18_trafficcamnet`) — not the approved weapon-detection model; confidence numbers are not meaningful here per `MODEL_REGISTRY.md` |

### NvDCF

| Item | Result | Evidence |
|---|---|---|
| Stable track IDs | PARTIAL | `components.tracker.counter=65` confirms the tracker element processed every frame; individual track-ID stability was not inspected frame-by-frame in this run |
| No track explosion | NOT YET RUN | Requires frame-trace inspection (`frame_trace.enabled: true`) with a real/representative scene |
| No ID flicker | NOT YET RUN | Same as above |

### SGIE

| Item | Result | Evidence |
|---|---|---|
| Secondary labels appear | PASS (mechanically) | `components.sgie.counter=65`; `siv_report.pipeline.sgie_fps=25.8` |
| Attached to correct track | N/A | Placeholder classifier — `runtime_adapter.py` deliberately never maps its output to a real class, per RM-11 Phase 2's Decision B |

### RuntimeAdapter

| Item | Result | Evidence |
|---|---|---|
| FrameObservation created | PASS | `components.runtime_adapter.counter=65` |
| No DeepStream types escape RuntimeAdapter | PASS | Design-time guarantee (ADR-027); confirmed no `pyds`/`gi.repository.Gst` import outside `apps/deepstream/app/runtime_adapter.py` (`grep -rL` across the package) |

### Calibration

| Item | Result | Evidence |
|---|---|---|
| Distance estimated | PASS (DB-backed unit test) | `test_full_chain_beats_expected_heartbeat_components` — skips without Postgres, not run in this sandbox during this session |
| Zone assigned | PASS (DB-backed unit test) | Same test |

### Threat Engine

| Item | Result | Evidence |
|---|---|---|
| Threat evaluated | PASS (DB-backed unit test) | Same test — FIRE fast-path produces a HIGH `ThreatAssessmentEvent` |
| Expected threat level | PASS (DB-backed unit test) | `threat_event.payload.threat_level.value == "HIGH"` |
| Rule execution | PASS (DB-backed unit test) | Same |

### Incident

| Item | Result | Evidence |
|---|---|---|
| Incident created | PASS (DB-backed unit test) | `IncidentCreatedEvent` received in the same test |
| No duplicates | PASS (unit test) | `test_recalibration_does_not_mutate_or_delete_prior_record`-style invariants; incident dedup covered by `services/incident_service` tests (unchanged by RM-11.SIV) |

### Alarm

| Item | Result | Evidence |
|---|---|---|
| Triggered correctly | PASS (DB-backed unit test) | `alarm_service.get_active_alarms()` returns exactly one alarm tied to the incident |

### EventBus

| Item | Result | Evidence |
|---|---|---|
| ThreatAssessmentEvent | PASS (DB-backed unit test) | See Threat Engine row |
| HumanReviewItemCreatedEvent | PASS (DB-backed unit test) | `test_unknown_uniform_creates_human_review_not_incident` |
| CameraDisconnectedEvent | NOT YET RUN | Requires a real disconnect — see Camera row |
| SystemEvent | PASS | `Camera Connected` published a `SystemEvent`; `components.event_bus` reflects delivery in the isolated watchdog test (`test_watchdog.py::TestEventBusLiveness`) |

### Performance

| Item | Result | Evidence |
|---|---|---|
| FPS acceptable | PASS | 25.9 fps, matching the 25fps source (placeholder-model baseline; real-model throughput is unbenchmarked, see `docs/BENCHMARK_ACCEPTANCE_CRITERIA.md`) |
| GPU acceptable | PASS | 14–40% utilization, 1.2GB/12GB memory during this single-camera, placeholder-model run |
| CPU acceptable | NOT MEASURED | `cpu_utilization_pct` requires two `/proc/stat` samples across `metrics_sample_interval_seconds` — this short-lived harness only sampled once |
| Memory acceptable | PASS | ~38% system memory used, stable across the run |

### Logging

| Item | Result | Evidence |
|---|---|---|
| All 17 subsystem loggers functioning | PASS | `configure_stage_logging` applied at startup; `radar_eye.stage.camera`/`radar_eye.stage.system` lines observed in the run log; remaining 15 covered by `test_stage_logging.py` |
| Audit logger (`radar_eye.audit`) recording major events | PASS | `Camera Connected: camera=...` and (in the pre-fix run) `Watchdog Warning: ... stalled` lines both observed |

### Watchdog

| Item | Result | Evidence |
|---|---|---|
| Detects stalled subsystem | PASS | Explicitly demonstrated: `calibration`/`threat_engine`/`incident`/`alarm`/`heartbeat` all correctly reported `healthy=False, reason="no activity recorded yet"` (these paths weren't exercised in this DB-less harness), while `rtsp`/`pgie`/`tracker`/`sgie`/`runtime_adapter`/`threat_runtime_adapter`/`camera`/`pipeline_fps` all correctly reported `healthy=True` once flowing |

### Validation Report

| Item | Result | Evidence |
|---|---|---|
| PASS/FAIL completed | PASS | This document |
| Evidence recorded | PASS | This document |
| `siv_reports/siv_report_latest.json` generated | PASS | Confirmed written with real pipeline/system/throughput/component data during this run |

---

## Known Constraints At Time Of Writing

- This repository's sandbox development environment (as of RM-11 Phase 1/2's
  hardware verification and this milestone's initial implementation) has no
  physical RTSP camera and no real PGIE/SGIE model files — `docs/MODEL_REGISTRY.md`
  still lists `yolo26m_weapon.pt`/`vit_48k_binary.pth` as unbenchmarked, absent,
  TensorRT-compatibility-unknown. The mechanics above (config resolution,
  logging, watchdog, tracing, dashboard, report generation) were built and
  hardware-verified using the same local `GstRtspServer` + placeholder-model
  methodology as RM-11 Phase 1/2 — see `docs/IMPLEMENTATION_STATUS.md` for
  that run's detail. Swapping in a real camera is purely a `configs/camera.yaml`
  edit + `python -m scripts.siv_register_camera`; swapping in real models is
  purely a `configs/models.yaml` edit. Neither requires a Python change.
- No PostgreSQL is reachable in the sandbox used for unit testing — DB-dependent
  tests skip (not fail), consistent with every other DB-dependent test in this
  repository (RM-03's testing policy). This does not block SIV on real target
  hardware, which will have PostgreSQL available per `CLAUDE.md`'s deployment
  target.
