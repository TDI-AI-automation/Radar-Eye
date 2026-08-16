# Production Validation Checklist

PASS/FAIL checklist for the first end-to-end manual UI validation run.
Fill this in live against the running system with **Production Validation
Mode** enabled (`configs/validation.yaml`'s `production_validation_mode.
enabled: true` — see `docs/CAMERA_RUNTIME_LIFECYCLE.md` and
`PRODUCTION_VALIDATION_MODE.md` for what that turns on). Where a row names
a specific dashboard line or log signal, that is exactly what to look at —
this checklist doesn't ask for anything Production Validation Mode
doesn't already surface.

Date: __________  Operator: __________  Commit: __________

---

## Camera

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 1 | RTSP connects | Dashboard `Camera`/`RTSP` rows show `✓ Alive`; `radar_eye.stage.camera` logs `Camera <id> connected` | ☐ | |
| 2 | Reconnect works | Disconnect the camera (unplug/block RTSP); dashboard shows `RTSP ✗ STALLED`; audit log shows `Pipeline Restarted: camera=... attempt=N` after reconnect | ☐ | |
| 3 | Disconnect detected | `_audit_logger` line "Camera %s failure: %s" appears within one `heartbeat.stale_after_seconds.rtsp` window (5s default) | ☐ | |
| 4 | FPS stable | Dashboard `Pipeline FPS` steady near baseline (~24.7 FPS single camera) with no sustained drop | ☐ | |

## DeepStream

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 5 | Pipeline PLAYING | `DeepStream performance snapshot` logs appear; dashboard `Pipeline ✓ Alive` | ☐ | |
| 6 | Dynamic source add/remove | Delete, then re-register, a camera via the UI; within one Desired State poll tick (~1s) dashboard reflects the change, `Desired State synchronization: (...)` logged | ☐ | |
| 7 | No decoder errors | No `gst_nvinfer_logger` ERROR lines, no segfault in `journalctl -k` | ☐ | |

## PGIE

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 8 | Objects detected | Trace log shows `OBJECT DETECTED class=... conf=... bbox=...`; dashboard `PGIE ✓ Alive` | ☐ | |
| 9 | Confidence reasonable | Sampled `conf=` values in trace log are not near-zero/near-one outliers for the object class | ☐ | |

## NvDCF (Tracker)

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 10 | Stable tracking | Trace log `TRACK UPDATED track_id=N` — the same `track_id` persists across consecutive frames for one physical object | ☐ | |
| 11 | No track explosion | `track_id` values stay bounded for the number of real objects in frame, not climbing unboundedly with nothing moving | ☐ | |
| 12 | No excessive ID flicker | A stationary/slow object doesn't repeatedly get a new `track_id` every few frames | ☐ | |

## SGIE

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 13 | Secondary labels produced | Trace log `SECONDARY CLASSIFICATION label=...`; dashboard `SGIE ✓ Alive` | ☐ | |
| 14 | Attached to correct tracks | The `[camera:frame]` correlation id ties `SECONDARY CLASSIFICATION` to the same frame's `TRACK UPDATED` line | ☐ | |

## RuntimeAdapter

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 15 | Observations created | Trace log `FRAME OBSERVATION CREATED detections=N`; dashboard `RuntimeAdapter ✓ Alive` | ☐ | |
| 16 | No DeepStream types escape the adapter | Code-level invariant (ADR-027) — not something to check live; confirmed by `RuntimeAdapter` being the sole `pyds`-touching module. Check off if no `pyds`/`Gst` object appears anywhere downstream in application logs (it never should). | ☐ | |

## Calibration

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 17 | Distance estimated | Trace log `CALIBRATION RESULT zone=... distance=...m` | ☐ | |
| 18 | Zone assigned | Same line's `zone=` is one of `zone_1`/`zone_2`/`zone_3` | ☐ | |

Requires the camera to be calibrated first (`POST`/calibration UI flow) —
if not yet calibrated, `Calibration` will show `✗ STALLED` on the
dashboard and this section cannot PASS yet; that is expected, not a
defect.

## ThreatEngine

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 19 | Threat evaluated | Trace log `THREAT ASSESSMENT level=... rule=...`; dashboard `ThreatEngine ✓ Alive`, `Threats/sec` non-zero while testing | ☐ | |
| 20 | Expected threat level | The resulting `level=` matches what the test scenario (weapon type + classification + zone) should produce per `docs/THREAT_ENGINE_SPEC.md`'s rule table | ☐ | |

## IncidentService

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 21 | Incident created | Trace log `INCIDENT CREATED incident_id=...` for a MEDIUM/HIGH/HUMAN_REVIEW assessment | ☐ | |
| 22 | No duplicate incidents | Same escalation (same track) doesn't produce more than one `INCIDENT CREATED` line | ☐ | |

## AlarmService

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 23 | Alarm triggered correctly | Trace log `ALARM GENERATED` appears only for HIGH threat assessments (per CLAUDE.md's Alarm Rules — HIGH is alarm-eligible, MEDIUM/LOW/ALLY/OBSERVE are not) | ☐ | |

## EventBus

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 24 | `ThreatAssessmentEvent` | Trace log `EVENT PUBLISHED ThreatAssessmentEvent`; dashboard `EventBus ✓ Alive`, `Events/sec` non-zero | ☐ | |
| 25 | `HumanReviewItemCreatedEvent` | Published for an `unknown` uniform classification (CLAUDE.md: unknown uniforms must never be auto-resolved) | ☐ | |
| 26 | `CameraDisconnectedEvent` | Published when the Camera check #2/#3 disconnect above occurs | ☐ | |
| 27 | `SystemEvent` | Published for a watchdog-detected stall or comparable system-level condition | ☐ | |

## Performance

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 28 | FPS acceptable | Dashboard `Pipeline FPS` / `PGIE FPS` / `SGIE FPS` near the established baseline (~24.7 FPS, single camera) | ☐ | |
| 29 | GPU acceptable | Dashboard `GPU` utilization within expected range for this hardware (baseline run: ~20%, single camera, real models) | ☐ | |
| 30 | GPU memory acceptable | Dashboard `Mem:` well under `gpu_memory_total_mb` | ☐ | |
| 31 | CPU acceptable | Dashboard `CPU` not pegged/sustained near 100% | ☐ | |
| 32 | RAM acceptable | Dashboard `RAM` stable, not climbing over the test duration (leak indicator) | ☐ | |

## Logging

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 33 | Every subsystem logging | With Production Validation Mode on, each of the 18 `radar_eye.stage.*` loggers is at DEBUG (`enable_maximum_observability()`); confirm at least the subsystems actually exercised in this run produced output | ☐ | |
| 34 | Stage logging complete | `radar_eye.trace` log shows the full chain for at least one real detection: FRAME RECEIVED → OBJECT DETECTED → TRACK UPDATED → SECONDARY CLASSIFICATION → FRAME OBSERVATION CREATED → CALIBRATION RESULT → THREAT ASSESSMENT → (INCIDENT CREATED) → (ALARM GENERATED) → EVENT PUBLISHED | ☐ | |

## Watchdog

| # | Check | Signal to look at | PASS/FAIL | Notes |
|---|---|---|---|---|
| 35 | Detects stalled subsystem | Cause a real stall (e.g. disconnect RTSP); within `watchdog.check_interval_seconds` (2s default) the dashboard row flips to `✗ STALLED` and `radar_eye.audit` logs `Watchdog Warning: <component> stalled -- ...` | ☐ | |

---

**Overall result:** ☐ PASS ☐ FAIL ☐ PASS WITH NOTED EXCEPTIONS

**Summary of failures / follow-ups:**




