# Production Run Guide — First End-to-End UI Validation

Every command below was verified against this repository and this machine
during this session (real camera, real models, real production
entrypoints — never `run_siv.py`, never a validation script). Copy-paste
ready as written.

---

## 1. Preconditions

- PostgreSQL reachable at `localhost:5432`, database `radar_eye` already
  exists, and the role in `.env`'s `RADAR_EYE_DB_USER`/
  `RADAR_EYE_DB_PASSWORD` can connect to it (`configs/settings.yaml`'s
  `database:` section — this guide does not create the role/database,
  only migrates schema inside it).
- `.env` exists at the repo root (copy from `.env.example` if not) with
  real values for `RADAR_EYE_DB_USER`, `RADAR_EYE_DB_PASSWORD`,
  `RADAR_EYE_ENCRYPTION_KEY`, `RADAR_EYE_JWT_SECRET`,
  `RADAR_CAMERA_USERNAME`, `RADAR_CAMERA_PASSWORD`.
- `.venv` exists at the repo root with dependencies already installed
  (this session used it throughout — see §2 if a fresh install is ever
  needed).
- `configs/models.yaml` already points `pgie`/`sgie` at real model files
  (`enabled: true` for both, confirmed on this machine at
  `/home/dev/Downloads/DeepStream-Yolo/`) — no action needed unless that
  changed.
- `configs/validation.yaml`'s `production_validation_mode.enabled` set to
  `true` for this run (see `docs/PRODUCTION_VALIDATION_MODE.md`) —
  **default is `false`**, so this must be edited before starting.
- **Port 8000 free.** A pre-existing `uvicorn` process was found already
  bound to `127.0.0.1:8000` on this machine while verifying this guide
  (PID 8209, running since 2026-07-28 11:26 — not started during this
  validation effort, origin unknown). Check before starting the API:
  ```bash
  pgrep -af uvicorn
  ```
  If something is already running there, decide whether it's safe to stop
  before starting a fresh instance for this run — don't assume it's safe
  to kill without knowing what it is.
- At least one physical RTSP camera reachable on the network, or the one
  already used throughout this session's hardware validation
  (`rtsp://192.168.68.10:554/Streaming/Channels/101`).
- `frontend/node_modules` already installed (confirmed present).

## 2. Terminal Commands

**Repository root:**
```bash
cd /home/dev/Documents/Army/Radar-Eye
```

**Virtual environment activation:**
```bash
source .venv/bin/activate
```

**Dependency installation (only if `.venv` is missing or out of date):**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

**Environment variables** (this repo does not auto-load `.env` — export
it into the shell before starting either backend process):
```bash
set -a
source .env
set +a
```

**Database migration:**
```bash
alembic -c apps/api/alembic.ini upgrade head
```

**Enable Production Validation Mode** (edit before starting — verified
against the current file, only touches the `production_validation_mode`
block, not `frame_trace`'s own separate `enabled: false` line):
```bash
python -c "
import re
path = 'configs/validation.yaml'
text = open(path).read()
text = re.sub(r'(production_validation_mode:\n  enabled: )false', r'\1true', text)
open(path, 'w').write(text)
"
```
Or simply open `configs/validation.yaml` in an editor and change that one
line under `production_validation_mode:` to `enabled: true`.

**API startup command** (its own terminal, repo root, venv active, `.env`
exported):
```bash
uvicorn apps.api.app.main:create_app --factory --reload
```

**DeepStream startup command** (its own terminal, repo root, venv active,
`.env` exported — this is the real production entrypoint; never
`scripts/run_siv.py`):
```bash
python -m apps.deepstream.app.main
```

**Frontend startup command** (its own terminal, no venv needed):
```bash
cd frontend
bun run dev
```
Defaults to `http://localhost:8000` for the API and `ws://localhost:8000`
for WebSocket (`frontend/src/api/instance.ts`/`ws/connection.ts`) — no
`.env` needed as long as the API runs on its default port 8000 (uvicorn's
default, matching the command above).

## 3. IDE Instructions

No `.vscode/launch.json` exists in this repository (checked) — there is
no pre-built debug configuration to select. Run each process in its own
VSCode integrated terminal (`` Ctrl+` ``, or the `+` button to open
another), one terminal per §2 command (API, DeepStream, frontend), each
in the repo root with the venv activated where applicable. Select the
`.venv` interpreter for any Python file navigation/IntelliSense
(`Ctrl+Shift+P` → "Python: Select Interpreter" → `.venv/bin/python`).
Do not run the DeepStream process through a debugger/breakpoint session
for this validation run — it must behave exactly as production would.

## 4. Runtime Expectations

**Expected startup order** (see `docs/CAMERA_RUNTIME_LIFECYCLE.md` §1 for
the full rationale): API first (frontend needs it immediately), then
DeepStream (independent of the API process, RM-14's process composition
is still undecided — see the "RM-14" row in §7), then frontend.

**Expected initialization logs**, DeepStream terminal, in order:
1. `"radar-eye-deepstream starting"`
2. (if Production Validation Mode is on) a `WARNING`-level
   `"Production Validation Mode ENABLED -- maximum observability active..."`
3. `"Initial Desired State synchronization: (...)"` — empty tuple if no
   camera is yet `OPERATIONAL` in Camera Registry, or
   `add_source:<id>`/`enable_ai:<id>` if one already is
4. NVIDIA `nvinfer` engine-deserialization lines for `sgie` then `pgie`
   (on **stderr** — native plugin logging, not this application's own)
5. `"radar-eye-deepstream running"`
6. Periodic `"DeepStream performance snapshot: ..."` and
   `"Camera Runtime telemetry snapshot: ..."` lines (every
   `metrics_sample_interval_seconds`, default 2s)

**Healthy system indicators:**
- `inference_fps`/`pgie_fps`/`sgie_fps` near 24.7 (single camera, this
  hardware's established baseline) and stable, not trending down.
- `end_to_end_latency_ms` in the single-digit milliseconds once past the
  first ~10s warm-up window (early snapshots can show 100+ ms while
  TensorRT engines finish loading — expected, not a defect).
- `readiness=ReadinessState(pipeline_ready=True, runtime_supervisor_ready=True, bridge_ready=True, event_bus_ready=True, database_ready=True)`
  in every telemetry snapshot.
- No `journalctl -k` segfault lines, no `Traceback`/`CRITICAL` in the
  DeepStream terminal.

**Expected dashboard output** (stderr, only if Production Validation Mode
is on — see `docs/PRODUCTION_VALIDATION_MODE.md` for why it's on stderr):
a redrawing table titled `RADAR EYE -- RM-11.SIV SYSTEM INTEGRATION
VALIDATION DASHBOARD`, with `Pipeline`/`Camera`/`RTSP`/`PGIE`/`NvDCF
(Tracker)`/`SGIE`/`RuntimeAdapter`/`ThreatEngineRuntimeAdapter` showing
`✓ Alive` once a camera is connected and streaming; `Calibration`/
`ThreatEngine`/`IncidentService`/`AlarmService`/`EventBus` correctly
showing `✗ STALLED` until an actual detection/calibration/threat/incident/
event occurs — that is expected, not a failure, until you exercise those
paths from the UI.

## 5. Manual UI Validation Checklist

Use `docs/PRODUCTION_VALIDATION_CHECKLIST.md` for the full PASS/FAIL
table. Exact sequence to execute from the frontend:

1. Log in.
2. **Camera management**: register the physical camera (name, RTSP URL,
   credentials, transport) via the UI's camera registration flow — it
   connects automatically, with no intermediate lifecycle state to
   promote through.
3. Confirm the camera connects — within one Desired State poll tick
   (~1s), confirm the DeepStream dashboard shows `Camera`/`RTSP ✓ Alive`
   and the pipeline picks it up
   (`Desired State synchronization: ('add_source:...',)` in the
   DeepStream terminal).
4. **Live camera view**: open it, confirm the UI reflects a connected
   camera (full video streaming is out of scope — Media Publisher ships
   with no default transport yet, see §7).
5. **Disable AI**, confirm the dashboard/log show `disable_ai` converge
   within one poll tick; **Enable AI** again, confirm `enable_ai`
   converges the same way.
6. **Delete/re-register cycle**: delete the camera, confirm
   `remove_source` converges cleanly (no crash — this exact operation is
   what the `remove_source()` pad-lifecycle fix targets, and the runtime
   fully releases its state — see `docs/CAMERA_RUNTIME_LIFECYCLE.md` §6);
   re-register the same physical camera and confirm `add_source`
   reconverges and it connects again without restarting any process.
7. Trigger a real detection in front of the camera (per the test
   scenario you're validating against `docs/THREAT_ENGINE_SPEC.md`'s
   rule table) and follow it end to end using
   `docs/PRODUCTION_VALIDATION_CHECKLIST.md`'s PGIE through EventBus
   sections.
8. **AI view**: confirm detections/tracks/classifications surface in the
   UI as they occur.
9. Repeat step 7 for each threat level / uniform classification scenario
   you need to validate (ALLY, OBSERVE, LOW, MEDIUM, HIGH, HUMAN_REVIEW).
10. Confirm **Telemetry** (dashboard `Heartbeat`, active/AI-enabled
    camera counts) and **Latency**/**Stability**/**UI responsiveness**
    hold up over the full session.

## 6. Log Locations

This repository has **no persistent log files by default** — confirmed:
`apps/api/app/logging_config.py`'s `configure_logging()` attaches a
stdout-only JSON handler; nothing in the codebase writes application logs
to disk. Everything below is a *stream*, not a file, unless you redirect
it yourself.

| What | Where | How to capture it |
|---|---|---|
| Application logs (both processes) | stdout, structured JSON | `python -m apps.deepstream.app.main >deepstream.log 2>deepstream.err` / same pattern for `uvicorn` |
| Subsystem logs (`radar_eye.stage.*`) | Same stdout stream, `"name"` field identifies the logger | `grep '"name": "radar_eye.stage.pgie"' deepstream.log` |
| Frame-level trace (`radar_eye.trace`) | Same stdout stream, only present when `frame_trace.enabled` or Production Validation Mode is on | `grep '"name": "radar_eye.trace"' deepstream.log` |
| Audit log (`radar_eye.audit`) | Same stdout stream — operator-facing major events (camera connect/disconnect, threats, incidents, alarms, watchdog warnings, pipeline restarts) | `grep '"name": "radar_eye.audit"' deepstream.log` |
| Performance/telemetry | Same stdout stream, periodic `"DeepStream performance snapshot"` / `"Camera Runtime telemetry snapshot"` lines | `grep "performance snapshot\|telemetry snapshot" deepstream.log` |
| Console dashboard | **stderr**, only when Production Validation Mode is on | Redirect separately: `2>dashboard.log`, or leave on screen |
| NVIDIA native plugin logs (TensorRT engine load, `nvinfer`/`nvtracker`) | stderr | Same `deepstream.err` file as above |
| Crashes (segfaults) | **Not in application output at all** — the kernel logs them | `journalctl -k --since "-10 min" \| grep -i segfault` |
| AI logs (detections, threat assessments) | `radar_eye.trace` (per-frame) and `radar_eye.stage.threat_engine`/`radar_eye.stage.calibration` (structural events) | Same stdout stream, filter by `"name"` |
| Event logs (`ThreatAssessmentEvent`, etc.) | `radar_eye.trace`'s `EVENT PUBLISHED <type>` lines | `grep "EVENT PUBLISHED" deepstream.log` |

## 7. Shutdown Procedure

In each terminal, in this order — frontend first (nothing depends on
it), then either backend process (they're independent of each other):

1. **Frontend**: `Ctrl+C` in its terminal (`bun run dev`'s dev server).
2. **DeepStream**: `Ctrl+C` (SIGINT) in its terminal. Expected log
   sequence: `"radar-eye-deepstream shutting down"` → NVIDIA
   `[NvMultiObjectTracker] De-initialized` → `"Executing AlarmService
   fail-safe shutdown..."` → process exits. This runs
   `DeepStreamRuntime.stop()`'s full reverse-order teardown — see
   `docs/CAMERA_RUNTIME_LIFECYCLE.md` §5 for exactly what happens and why
   that order is safe. Typically completes in under 2 seconds.
3. **API**: `Ctrl+C` in its terminal (uvicorn's own graceful shutdown).
4. Confirm no process remains: `pgrep -af "apps.deepstream.app.main|uvicorn apps.api"`
   should return nothing.
5. If Production Validation Mode was enabled for this run, set
   `configs/validation.yaml`'s `production_validation_mode.enabled` back
   to `false` before the next normal production run.
