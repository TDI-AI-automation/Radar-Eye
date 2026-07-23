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
| Date | _(fill in)_ |
| Camera | _(fill in — matches `configs/camera.yaml`'s `camera_id`)_ |
| PGIE model | _(fill in, or "placeholder — `pgie.enabled: false`")_ |
| SGIE model | _(fill in, or "placeholder — `sgie.enabled: false`")_ |
| `siv_reports/` file | _(fill in filename)_ |
| Operator | _(fill in)_ |

---

## Checklist

Every item: **PASS** / **FAIL** / **NOT YET RUN**, plus Evidence.

### Camera

| Item | Result | Evidence |
|---|---|---|
| RTSP connects | | |
| Reconnect works | | |
| Disconnect detected | | |
| FPS stable | | |

### DeepStream

| Item | Result | Evidence |
|---|---|---|
| Pipeline PLAYING | | |
| Pipeline restart | | |
| No decoder errors | | |

### PGIE

| Item | Result | Evidence |
|---|---|---|
| Objects detected | | |
| Confidence reasonable | | |

### NvDCF

| Item | Result | Evidence |
|---|---|---|
| Stable track IDs | | |
| No track explosion | | |
| No ID flicker | | |

### SGIE

| Item | Result | Evidence |
|---|---|---|
| Secondary labels appear | | |
| Attached to correct track | | |

### RuntimeAdapter

| Item | Result | Evidence |
|---|---|---|
| FrameObservation created | | |
| No DeepStream types escape RuntimeAdapter | | (design-time guarantee — ADR-027; verify no `apps/deepstream/app/threat_runtime_adapter.py` or downstream import of `pyds`/`gi.repository.Gst`) |

### Calibration

| Item | Result | Evidence |
|---|---|---|
| Distance estimated | | |
| Zone assigned | | |

### Threat Engine

| Item | Result | Evidence |
|---|---|---|
| Threat evaluated | | |
| Expected threat level | | |
| Rule execution | | |

### Incident

| Item | Result | Evidence |
|---|---|---|
| Incident created | | |
| No duplicates | | |

### Alarm

| Item | Result | Evidence |
|---|---|---|
| Triggered correctly | | |

### EventBus

| Item | Result | Evidence |
|---|---|---|
| ThreatAssessmentEvent | | |
| HumanReviewItemCreatedEvent | | |
| CameraDisconnectedEvent | | |
| SystemEvent | | |

### Performance

| Item | Result | Evidence |
|---|---|---|
| FPS acceptable | | |
| GPU acceptable | | |
| CPU acceptable | | |
| Memory acceptable | | |

### Logging

| Item | Result | Evidence |
|---|---|---|
| All 17 subsystem loggers functioning | | |
| Audit logger (`radar_eye.audit`) recording major events | | |

### Watchdog

| Item | Result | Evidence |
|---|---|---|
| Detects stalled subsystem | | |

### Validation Report

| Item | Result | Evidence |
|---|---|---|
| PASS/FAIL completed | | |
| Evidence recorded | | |
| `siv_reports/siv_report_latest.json` generated | | |

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
