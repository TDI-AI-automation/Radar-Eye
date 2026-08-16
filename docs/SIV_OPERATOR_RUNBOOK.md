# RM-11.SIV — Operator Runbook

For running a real-camera / real-model System Integration Validation session
**without touching any Python code.** Every step below is either a config
edit or a command. If you find yourself needing to edit anything under
`apps/deepstream/app/`, stop — that means something this runbook assumes is
missing, not something you should patch by hand; raise it instead.

**Files you may edit — nothing else:**

| File | Purpose | Required? |
|---|---|---|
| `.env` | DB/encryption credentials (create once from `.env.example`) | Always |
| `configs/models.yaml` | PGIE/SGIE model paths, precision, thresholds | Always |
| `configs/camera.yaml` | The one camera's RTSP details (create from `.example`) | Always |
| `configs/validation.yaml` | Watchdog thresholds, frame trace on/off, feature flags | Optional |
| `configs/logging.yaml` | Per-subsystem log level overrides | Optional |
| `configs/visualization.yaml` | Operator-visible RTSP video overlay (bounding boxes, track IDs, SGIE/threat labels) | Optional |

`configs/settings.yaml` (streammux/tracker/reconnect defaults) is also
technically editable but nothing below requires touching it. `.env` is
gitignored — creating/editing it never touches version control.

---

## Decision Tree

Every step below gates the next one. If a step fails, stop, resolve the
reported issue, and restart from `check_environment.py` — don't skip ahead
on the assumption a later step will "probably still work."

```
Start
  |
  v
check_environment.py
  |
  v
PASS? --NO--> STOP: resolve the reported issue, restart from
  |                 check_environment.py
 YES
  |
  v
check_models.py
  |
  v
PASS? --NO--> STOP: fix configs/models.yaml, restart from
  |                 check_environment.py
 YES
  |
  v
siv_register_camera.py
  |
  v
PASS? --NO--> STOP: fix configs/camera.yaml / .env, restart from
  |                 check_environment.py
 YES
  |
  v
show_registered_cameras.py
  |
  v
PASS? --NO--> STOP: registration didn't commit, restart from
  |                 check_environment.py
 YES
  |
  v
check_rtsp.py
  |
  v
PASS? --NO--> STOP: fix camera network/credentials, restart from
  |                 check_environment.py
 YES
  |
  v
run_siv.py
  |
  v
Dashboard (live monitoring)
  |
  v
Physical Validation (operator observes real detections)
  |
  v
Generate Reports (siv_report.json + SIV_VALIDATION_REPORT.md)
  |
  v
SIV Complete
```

If **any** step fails, the operator must stop, resolve the reported issue,
and restart from `check_environment.py` — not from the step that failed.
An environment problem (driver, disk space, a stale `.env`) can silently
invalidate an earlier "PASS" from before it changed.

---

## 0. Prerequisites (one-time, verify don't assume)

0.1. `cd` to the repository root. Every command below assumes you're there
(`python -m scripts.xxx` resolves the `scripts` package relative to cwd).

0.2. Confirm you're on the right interpreter — the one with `gi`/`pyds`
(DeepStream's Python bindings) installed. On this reference machine that's
the system Python, not the repo's miniconda pytest environment:

```bash
python3.10 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('OK')"
```
**Expected:** `OK`. **If this fails:** you're on the wrong interpreter, or
the DeepStream/GStreamer SDK isn't installed on this machine — this runbook
assumes it already is (see `docs/IMPLEMENTATION_STATUS.md`'s "Reference
environment (RM-11)" row for how it was set up here).

0.3. Create `.env` if it doesn't already exist (every DB-touching command
below — steps 1, 7, 8, 9 — needs `RADAR_EYE_DB_USER`/`RADAR_EYE_DB_PASSWORD`/
`RADAR_EYE_ENCRYPTION_KEY`; without it they fail with a pydantic
`ValidationError` before even attempting a connection, not a clearer
"can't connect" message):

```bash
test -f .env || cp .env.example .env
# then edit .env and fill in real values
```
If you'll use `${RADAR_CAMERA_USERNAME}`/`${RADAR_CAMERA_PASSWORD}`-style
substitution in `configs/camera.yaml` (step 4), add those two variables to
`.env` as well, then `set -a; source .env; set +a` in your shell before
steps 5/7/9 — `.env` is only auto-loaded by the DB/encryption settings
class, not by the plain `os.environ` lookup `configs/camera.yaml`'s
substitution uses.

0.4. Confirm PostgreSQL is reachable (required for camera registration and
for Calibration/Threat Engine/Incident/Alarm — not for the two pre-flight
checks in steps 3 and 5; step 1's `check_environment.py` also checks this
automatically, this manual version is only useful before `.env` exists):

```bash
python -c "
import asyncio
from apps.api.app.config import get_settings
from apps.api.app.db import create_engine
async def main():
    engine = create_engine(get_settings())
    try:
        async with engine.begin(): print('POSTGRES REACHABLE')
    except Exception as e: print('NOT REACHABLE:', e)
    finally: await engine.dispose()
asyncio.run(main())
"
```
**Expected:** `POSTGRES REACHABLE`. **If it raises a `ValidationError`
instead:** step 0.3 wasn't completed — `.env` is missing or incomplete.
**If it prints `NOT REACHABLE: ...`:** `.env` is read correctly but the
database itself isn't up/reachable — fix that before step 7.

0.5. Backend Database Initialization — if using a fresh PostgreSQL database
(reachable per 0.4, but never migrated), the schema does not exist yet.
Nothing in this repository applies migrations automatically — not
`apps/api/app/main.py`'s startup, not `scripts/run_siv.py`,
`check_environment.py`. Skipping this step is the single most common cause
of a healthy-looking backend that still reports `database: unhealthy`
(`/health/system`'s `CameraRepository.list()` query fails with
`asyncpg.exceptions.UndefinedTableError: relation "cameras" does not
exist`, since nothing has created the table yet):

1. Activate the project's virtual environment.
2. Run, from the repository root (`env.py` reads `.env` relative to the
   current working directory):
   ```bash
   alembic -c apps/api/alembic.ini upgrade head
   ```
   **Expected:** ends with `Running upgrade 3bb1f0f0a294 -> 1f216fe63fe1,
   audit_log`, no traceback, exit code `0`.
3. Verify with the backend running:
   ```bash
   curl -s http://127.0.0.1:8000/health/system
   ```
   **Expected:** `"success": true` and `"data"` showing `db_healthy: true`.

---

## 1. Validate the environment — `check_environment.py`

The very first command of every SIV session, before anything else in this
runbook:

```bash
python scripts/check_environment.py
```
(Works under either interpreter for the checks that don't need `gi`/`pyds`;
GPU/driver/CUDA/TensorRT/DeepStream/GStreamer checks need the real
DeepStream environment — run it under the system interpreter, step 0.2, for
a fully meaningful result.)

**Expected output (PASS):**
```
✓ Python version: 3.10.12
✓ Python packages: requirements.txt satisfied
✓ Environment variables: RADAR_EYE_DB_USER, RADAR_EYE_DB_PASSWORD, RADAR_EYE_ENCRYPTION_KEY
✓ GPU: GPU 0: NVIDIA ...
✓ NVIDIA Driver: 535.xx
✓ CUDA: 12.2
✓ TensorRT: 8.6.1
✓ DeepStream: Version: 7.0.0
✓ GStreamer: GStreamer 1.20.3
✓ PostgreSQL: localhost:5432/radar_eye
✓ Model directory: exists
✓ Engine files: present
✓ Label files: present
✓ Disk space: 210.4 GB free at storage
✓ Writable output directories: storage, storage/snapshots, storage/recordings

RESULT: PASS
```

**On FAIL**, every failing check is listed by name with its exact reason, e.g.:
```
✗ PostgreSQL
✗ TensorRT

FAIL

PostgreSQL:
  [Errno 111] Connection refused

TensorRT:
  import tensorrt failed: No module named 'tensorrt'

Do not continue to the next SIV step until every check above passes.
```

**Pass/fail criteria:** exit code `0` and `RESULT: PASS` — **every** listed
check must pass, not just the ones relevant to what you're about to do next.
`configs/models.yaml`'s Model directory/Engine files/Label files checks
report PASS automatically when both `pgie`/`sgie` are `enabled: false`
(placeholder mode) — nothing to validate yet in that case.

**Do not proceed to step 2 (or any later step) until this is `RESULT: PASS`.**
If something about the environment changes mid-session (disk fills up,
`.env` gets edited, a cable gets unplugged), re-run this step before
trusting any later step's result.

---

## 2. Edit `configs/models.yaml`

Open `configs/models.yaml`. For each of `pgie:`/`sgie:`:
- Set `enabled: true` and fill in `model_file`/`engine_file`/`labels` with
  real absolute paths, **or**
- Leave `enabled: false` to use the RM-11 Phase 1/2 placeholder model for
  that stage (fine for a mechanics-only dry run before real models are
  ready).

If your model needs the custom bbox-parser plugin (a custom-trained
detector — see `apps/deepstream/native/README.md`), also set
`custom_lib_path`/`parse_bbox_func_name`/`cluster_mode: 4`. Build the
plugin first if you haven't:

```bash
./scripts/build_yolo_parser.sh
```
**Expected:** ends with `Built: apps/deepstream/native/nvdsinfer_custom_impl_Yolo/libnvdsinfer_custom_impl_Yolo.so`.
**Pass/fail:** a non-zero exit / compiler error means either `CUDA_VER` is
wrong (pass it explicitly: `./scripts/build_yolo_parser.sh 12.2`) or the
DeepStream SDK headers aren't where the Makefile expects
(`/opt/nvidia/deepstream/deepstream/sources/includes`).

---

## 3. Validate `configs/models.yaml` — `check_models.py`

```bash
python -m scripts.check_models
```
(No `gi` needed — this works under any Python with this repo's
dependencies, including the miniconda one.)

**Expected output** (placeholder example):
```
Reading /path/to/repo/configs/models.yaml

[pgie]
  enabled:    False
  -> placeholder config will be used (RM-11 Phase 1/2 stock model)

[sgie]
  enabled:    False
  -> placeholder config will be used (RM-11 Phase 1/2 stock model)

PASS [pgie]: placeholder -> apps/deepstream/configs/pgie_placeholder.txt
PASS [sgie]: placeholder -> apps/deepstream/configs/sgie_placeholder.txt

RESULT: PASS
```
With real models enabled, each `PASS` line instead reads
`resolved (custom model) -> apps/deepstream/configs/generated/{pgie,sgie}_resolved.txt`.

**Pass/fail criteria:** exit code `0` and `RESULT: PASS` for both stages.
**On FAIL:** the line above it names the exact `configs/models.yaml` key
and path that's wrong, e.g.:
```
FAIL [pgie]: configs/models.yaml: pgie.model_file = '/mnt/models/yolo26m_weapon.onnx' does not exist or is not a file.
```
Fix that path in `configs/models.yaml` and re-run. Add `--show-config` to
print the exact rendered `nvinfer` config for a resolved stage — useful for
double-checking `cluster-mode`/`operate-on-class-ids`/etc. before a full run.

**Do not proceed to step 7 until this is `RESULT: PASS`.**

---

## 4. Create and edit `configs/camera.yaml`

```bash
cp configs/camera.yaml.example configs/camera.yaml
```
Edit `configs/camera.yaml`: set `camera_id` (a short slug, e.g.
`north-gate-01`), `rtsp_url`, `transport`. For credentials, either put them
directly in `username`/`password`, or (preferred — keeps secrets out of the
file) reference environment variables:
```yaml
username: ${RADAR_CAMERA_USERNAME}
password: ${RADAR_CAMERA_PASSWORD}
```
and export them in your shell first: `export RADAR_CAMERA_USERNAME=... RADAR_CAMERA_PASSWORD=...`.

`configs/camera.yaml` is gitignored — it will never show up in `git status`
or accidentally get committed.

---

## 5. Validate RTSP connectivity — `check_rtsp.py`

```bash
python3.10 -m scripts.check_rtsp
```
(Needs `gi`/`Gst` — use the same interpreter as step 0.2, not miniconda.)

**Expected output (PASS):**
```
Reading /path/to/repo/configs/camera.yaml
Connecting to rtsp://***:***@192.168.1.50:554/stream1 (transport=tcp, timeout=15.0s)
PASS: reached PLAYING in 0.8s

RESULT: PASS
```
Credentials are always masked in the printed URL, even on success.

**Pass/fail criteria:** exit code `0` and `RESULT: PASS`.

**On FAIL — how to interpret:**
| Message contains | Likely cause |
|---|---|
| `Could not open resource` / `Failed to connect` | Wrong IP/port, camera offline, or a firewall/network path issue |
| `401`/`Unauthorized`/`authentication` | Wrong `username`/`password` (or the referenced env var isn't set/exported) |
| `timed out after Ns without reaching PLAYING` | Camera reachable at the TCP level but never completed the RTSP handshake — check `transport` (try the other of `tcp`/`udp`), or the camera's RTSP path/`rtsp_url` is wrong |
| `MissingEnvironmentVariableError` / mentions `${...}` | You used `${VAR_NAME}` in `camera.yaml` but never exported it in this shell |

Increase the timeout for a slow/high-latency camera: `--timeout 30`.

**Do not proceed to step 7 until this is `RESULT: PASS`.**

---

## 6. (Optional) Adjust `configs/validation.yaml` / `configs/logging.yaml`

- `configs/validation.yaml`: `frame_trace.enabled: true` turns on the full
  per-frame stage trace (FRAME RECEIVED → ... → EVENT PUBLISHED) on the
  `radar_eye.trace` logger — verbose, use for debugging a specific frame's
  path through the pipeline, not for a normal run. `watchdog.stale_after_seconds`
  controls how long a component can go silent before the watchdog flags it
  — the defaults (5-10s) are reasonable starting points; loosen them if
  your camera has a naturally bursty frame rate.
- `configs/logging.yaml`: raise any of the 17 `loggers:` entries to `DEBUG`
  for noisier diagnostics on one specific subsystem (e.g. `calibration: DEBUG`).

Neither file needs to be touched for a standard run — the checked-in
defaults are safe.

---

## 6.5. (Optional) Enable Visualization — `configs/visualization.yaml`

Renders directly from the pipeline's own PGIE/NvDCF/SGIE inference results
onto a live RTSP stream — bounding boxes, track IDs, classification, threat
level, zone/distance, FPS/latency. This is the production video-output
backend, not a debug-only tool, but it is entirely optional for SIV: leaving
it disabled changes nothing else in this runbook.

**Disabled (default):** `configs/visualization.yaml`'s `enabled: false` — a
fresh checkout never starts encoding or streaming. Skip straight to step 7.

**Enabled:** set `enabled: true`. Leave `stream_output_enabled: true` and
`rtsp_output_enabled: true` unless you have a specific reason not to publish
RTSP. Adjust `rtsp_port`/`stream_name` only if `8554`/`radar-eye` collide
with something else on this machine. The `draw_*` toggles and `color_scheme`
control what's overlaid — the checked-in defaults draw everything this
milestone supports.

**RTSP URL:** once `run_siv.py` (step 9) is running, its startup log prints
the exact URL:
```
Visualization stream live: rtsp://<this-machine-ip>:8554/radar-eye
```
Connect with any RTSP client, e.g.:
```bash
vlc rtsp://<this-machine-ip>:8554/radar-eye
# or
gst-launch-1.0 rtspsrc location=rtsp://<this-machine-ip>:8554/radar-eye latency=200 ! decodebin ! autovideosink
```

**Expected output:** a live video feed of the camera with, per object
detected: a colored bounding box (color by class — see
`configs/visualization.yaml`'s `color_scheme`, overridden by threat color
once a threat level is known: HIGH=red, MEDIUM=yellow, LOW=green), a text
label above/beside it (class, confidence, track ID, SGIE classification,
zone/distance/threat once calibration + threat engine have produced a
result for that track), and one frame-level overlay line (camera name,
timestamp, current FPS, pipeline latency). A client joining mid-stream may
show a stale/frozen frame for **up to ~1 second** before the first keyframe
arrives (`iframeinterval` is tuned to `output_fps`, i.e. one keyframe/sec) —
this is normal RTP/H.264 join behavior, not corruption.

**Verification checklist:**
- [ ] `run_siv.py`'s startup log shows `Visualization stream live: rtsp://...`
- [ ] An RTSP client SETUP/PLAY succeeds against that URL (VLC opens without
  an error dialog; `gst-launch-1.0` doesn't print `SDP contains no streams`)
- [ ] Bounding boxes track real detected objects, framerate matches live
  motion (not a frozen/stale image beyond the ~1s join delay above)
- [ ] Track IDs stay stable on a stationary/slow-moving object across frames
- [ ] Once a camera is calibrated (RM-05) and a track has a threat
  assessment, the box color switches to the threat-level color
- [ ] With `visualization.enabled: false`, `run_siv.py`'s dashboard and
  `siv_report.json` are unaffected — no `Visualization stream live` line,
  no `visualization_fps`/`overlay_time_avg_ms` in the performance snapshot

**Common failure modes and recovery steps:**

| Symptom | Meaning | Recovery |
|---|---|---|
| No `Visualization stream live` line; instead `Visualization enabled but not running: <reason>` | `VisualizationManager.initialize()`/`.start()` failed — logged and isolated, **inference is unaffected**, the run is still valid | Read the `reason` string (also in `radar_eye.stage.visualization` log lines). `Failed to attach RTSP server on port <N> (already in use...)`: another process is bound to `rtsp_port` — stop it or change `rtsp_port`. Any other reason: a GStreamer element failed to construct/link — check that the DeepStream/GStreamer install has `nvvideoconvert`/`nvdsosd`/`nvv4l2h264enc`/`GstRtspServer` available (same environment step 0.2 already validated) |
| Client connects but shows a solid green/gray frame that never updates | Almost always: client captured before the first real H.264 keyframe arrived — wait a couple of seconds and reconnect, or increase the client's jitter buffer/latency (`latency=200` above) | If it persists past ~5s, treat it as a real fault — restart `run_siv.py` and re-check the failure modes above |
| `SDP contains no streams` from an RTSP client | The client connected before `run_siv.py`'s RTSP server finished mounting, or the port/stream name in the client URL doesn't match `configs/visualization.yaml`'s `rtsp_port`/`stream_name` | Confirm the URL against the startup log line exactly; retry the client a few seconds after `run_siv.py` starts |
| No text labels, only boxes (or vice versa) | One or more `draw_*` toggles in `configs/visualization.yaml` is `false`, or a track hasn't yet produced the field being drawn (e.g. `draw_threat: true` but no threat assessment exists yet for that track) | Check the relevant `draw_*` toggle; for threat/zone/distance, confirm the camera is calibrated (RM-05) |
| Pipeline FPS/latency noticeably worse with visualization enabled | Expected — see `docs/SIV_BASELINE.md`'s Visualization OFF vs. ON table for measured deltas on this hardware (real-camera baseline: +5% latency, +~1GB GPU memory, no measurable inference FPS loss) | If the delta is far larger than that baseline, treat it as a real regression, not expected overhead — report it |

---

## 7. Register the camera — `siv_register_camera.py`

```bash
python -m scripts.siv_register_camera
```
(No `gi` needed — works under either interpreter, as long as PostgreSQL is
reachable, step 0.4.)

**Expected output:**
```
INFO:scripts.siv_register_camera:Created new camera <uuid> (north-gate-01)
INFO:scripts.siv_register_camera:Created new stream profile for camera <uuid>
INFO:scripts.siv_register_camera:Registered camera 'north-gate-01' (id=<uuid>) for RM-11.SIV
```
Re-running with the same `camera_id` is safe and idempotent — it updates
the existing row (`Reusing existing camera...` / `Updated existing stream
profile...`) instead of duplicating it, e.g. after changing the RTSP URL.

**Pass/fail:** no traceback, and a final `Registered camera '<slug>'` line.
**On FAIL:** a `MissingEnvironmentVariableError` means an env var referenced
in `camera.yaml` isn't exported; any DB connection error means step 0.4
wasn't actually satisfied — re-check it.

---

## 8. Confirm registration — `show_registered_cameras.py`

```bash
python -m scripts.show_registered_cameras
```

**Expected output:**
```
camera_id                            name           status        transport  rtsp_host                          created_at
------------------------------------  -------------  ------------  ---------  ----------------------------------  --------------------------
7f12c95d-ff8f-40a9-856e-1de985a4acdc  north-gate-01  DISCONNECTED  tcp        rtsp://192.168.1.50:554/stream1     2026-07-24T09:00:00+00:00
```
Credentials are never shown, even though this script had to decrypt the
stored URL to get this far. `status` will read `DISCONNECTED` here — it
only updates to `CONNECTED` once `run_siv.py` actually connects (step 9).

**Pass/fail:** your camera's slug appears in the table with the expected
`rtsp_host`. **On FAIL (empty table):** step 7 didn't actually commit —
re-run it and check for errors.

---

## 9. Start the SIV session — `run_siv.py`

```bash
python3.10 -m scripts.run_siv 2>&1 | tee siv_run_$(date +%Y%m%d_%H%M%S).log
```
(Needs `gi`/`pyds` — system interpreter, step 0.2. The `tee` is optional
but recommended — see "Logs" below for why.)

**Expected output, in order:**
1. Startup log lines (`RM-11.SIV starting`, model/pipeline construction,
   `Pipeline built...`, `Load new model:...sucessfully` for each stage if
   using real models — **first-run TensorRT engine builds can take 1-3+
   minutes**, this is normal, not a hang).
2. `Camera Connected: camera=<uuid>` (audit log line) once RTSP negotiates.
3. The live dashboard begins redrawing every 2 seconds (see below).

**Stop it** with a single `Ctrl+C` (SIGINT) — **not** `kill -9` / a second
Ctrl+C, which skips the graceful-shutdown path and the automatic
`siv_report.json` (step 10) never gets written. One Ctrl+C triggers:
`RM-11.SIV run stopping` → pipeline/watchdog/dashboard stopped cleanly →
`SIV report written to siv_reports/siv_report_<timestamp>.json`.

### Viewing the dashboard

`run_siv.py`'s dashboard clears and redraws your terminal every 2 seconds
— that redraw *is* the live view, no separate command needed. It looks
like:
```
================================================================
RADAR EYE -- RM-11.SIV SYSTEM INTEGRATION VALIDATION DASHBOARD
================================================================
Pipeline
  ✓ Alive  (count=65, last activity 0.0s ago)
  Pipeline FPS: 25.9
Camera
  ✓ Alive  (count=66, last activity 0.0s ago)
RTSP
  ✓ Alive  (count=66, last activity 0.0s ago)
PGIE
  ✓ Alive  (count=66, last activity 0.0s ago)
  PGIE FPS: 15.8
...
----------------------------------------------------------------
Latency:  110.2ms
GPU:      23.0%  Mem: 1231.0/12288.0 MB
CPU:      n/a  RAM: 38.9%
Model:    PLACEHOLDER (see configs/models.yaml)
Frames processed: 65
================================================================
```
`✓ Alive` = that component has produced output within its configured
staleness threshold (`configs/validation.yaml`). `✗ STALLED` = it hasn't —
see "Interpreting failures" below.

### Logs — where they're written

**Currently: stdout only** (structured JSON, one line per record) — there
is no separate log file written automatically. This is why the `tee`
command above matters: it lets you watch the live dashboard in your
terminal *and* capture everything (dashboard redraws included) to a file
for later review. To extract just the meaningful lines afterward (the
dashboard's screen-clear codes make the raw file noisy):
```bash
grep '"name": "radar_eye.audit"' siv_run_<timestamp>.log      # major operator events only
grep '"name": "radar_eye.stage.pgie"' siv_run_<timestamp>.log  # one subsystem's diagnostics
```

### Interpreting failures while it's running

| Symptom | Meaning | What to check |
|---|---|---|
| `Watchdog Warning: camera stalled` (or any component) | That component hasn't produced output within its threshold | Corresponding dashboard row shows `✗ STALLED` with a `reason:` line — start there |
| `rtsp`/`pgie`/`tracker`/`sgie` all `✗ STALLED`, `Pipeline FPS: n/a` | No frames flowing at all | Re-run step 5 (`check_rtsp.py`) — the camera may have dropped, or `nvstreammux`/`batched-push-timeout` needs adjusting in `configs/settings.yaml` if you have far more or fewer cameras than this was tuned for |
| `pgie`/`sgie` `✗ STALLED` but `rtsp`/`camera` `✓ Alive` | Frames are arriving but not reaching inference | Check `Load new model` succeeded in the startup log for that stage — an engine-build failure would show as a `WARN`/`ERROR` from `nvinfer` right after startup |
| `calibration`/`threat_engine`/`incident`/`alarm` `✗ STALLED` | No tracked detections have reached that stage yet | Expected until the detector actually reports objects with track IDs, or the camera hasn't been calibrated (RM-05 — this runbook doesn't cover calibration; a camera with no calibration row will never produce a distance estimate) |
| Bus `ERROR` message in the log | A real GStreamer/DeepStream pipeline fault | The message itself names the failing element — report it verbatim |

---

## 10. Generate the final artifacts

`siv_reports/siv_report_<timestamp>.json` and `siv_reports/siv_report_latest.json`
are written **automatically** on a clean shutdown (step 9's single
Ctrl+C) — no separate command. Confirm it exists:
```bash
cat siv_reports/siv_report_latest.json
```
**Expected:** a JSON object with `timestamp`/`pipeline`/`system`/`throughput`/`components`
sections, matching the dashboard's final numbers.

`docs/SIV_VALIDATION_REPORT.md` is **not** auto-generated — fill it in by
hand (or hand it plus `siv_reports/siv_report_latest.json` and your
captured log to whoever/whatever is completing the checklist):
1. Fill in the **Run Metadata** table at the top (date, camera, models used,
   which `siv_reports/` file, operator name).
2. For each checklist section (Camera, DeepStream, PGIE, NvDCF, SGIE, ...),
   mark **PASS**/**FAIL**/**NOT YET RUN** and cite evidence — a
   `siv_report.json` field, a specific log line, or a dashboard state you
   observed. The existing rows in the file already show the expected
   format from the placeholder-model verification run — follow that
   pattern with your own run's numbers.
3. If this run used real models/a real camera for the first time, also add
   a new row to **`docs/SIV_BASELINE.md`**'s Scaling Table (1-camera row,
   with your model name instead of "Placeholder") — that file is
   append-only, never overwrite a prior row.

---

## Quick Reference — Command Summary

```bash
# One-time / prerequisites
python3.10 -c "import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst; print('OK')"

# Per-session
python3.10 -m scripts.check_environment               # must PASS -- always first
cp configs/camera.yaml.example configs/camera.yaml   # first time only
# edit configs/models.yaml, configs/camera.yaml
python -m scripts.check_models                       # must PASS
python3.10 -m scripts.check_rtsp                      # must PASS
# optional: edit configs/visualization.yaml, set enabled: true
python -m scripts.siv_register_camera
python -m scripts.show_registered_cameras             # confirm
python3.10 -m scripts.run_siv 2>&1 | tee siv_run_$(date +%Y%m%d_%H%M%S).log
# Ctrl+C once when done
cat siv_reports/siv_report_latest.json
# fill in docs/SIV_VALIDATION_REPORT.md, optionally add a row to docs/SIV_BASELINE.md
```

If any command above fails, stop and restart the whole session from
`check_environment.py` once the reported issue is resolved — see the
Decision Tree at the top of this document.
