==================================================
SECTION 1
Repository
==================================================

Working directory:

/home/dev/Documents/Army/Radar-Eye

Verify I am in the correct directory:

pwd && ls apps/deepstream/app/main.py apps/api/app/main.py frontend/package.json

Expected output:

/home/dev/Documents/Army/Radar-Eye
apps/deepstream/app/main.py
apps/api/app/main.py
frontend/package.json

Check for already-running processes before starting anything:

pgrep -af "uvicorn|apps.deepstream.app.main|vite dev"

Expected output:

(empty, if nothing is running)

If this prints anything, a Backend API, DeepStream Runtime, or Frontend
process from an earlier session is still running. Note the PID(s). You
can either use what's already running (skip that section's start command
below) or stop it first with:

kill -TERM <PID>

==================================================
SECTION 2
Python Virtual Environment
==================================================

Do I need to activate a venv?

YES.

If YES:

Windows PowerShell:

.venv\Scripts\Activate.ps1

Windows CMD:

.venv\Scripts\activate.bat

Linux/macOS:

source .venv/bin/activate

Verify activation:

which python && python --version

Expected output:

/home/dev/Documents/Army/Radar-Eye/.venv/bin/python
Python 3.10.12

==================================================
SECTION 3
Environment
==================================================

Verify .env exists:

test -f .env && echo ".env FOUND" || echo ".env MISSING"

Expected output:

.env FOUND

Load it into this shell (required before every command below that talks
to the database or starts a backend process):

set -a
source .env
set +a

Verify required configuration:

PYTHONPATH=. python -c "from apps.api.app.config import get_settings; s = get_settings(); print('Settings loaded OK'); print('DB:', s.database.host, s.database.port, s.database.name)"

Expected output:

Settings loaded OK
DB: localhost 5432 radar_eye

If this raises a ValidationError instead, .env is missing one of:
RADAR_EYE_DB_USER, RADAR_EYE_DB_PASSWORD, RADAR_EYE_ENCRYPTION_KEY,
RADAR_EYE_JWT_SECRET.

==================================================
SECTION 4
Database
==================================================

Run migrations:

alembic -c apps/api/alembic.ini upgrade head

Expected output (first run, empty database):

INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 3bb1f0f0a294, initial schema
INFO  [alembic.runtime.migration] Running upgrade 3bb1f0f0a294 -> 1f216fe63fe1, audit_log
INFO  [alembic.runtime.migration] Running upgrade 1f216fe63fe1 -> 7a2c4e9d1b3f, camera_lifecycle_state
INFO  [alembic.runtime.migration] Running upgrade 7a2c4e9d1b3f -> 9c1f6b4a2e7d, camera_desired_state_flags

Expected output (already migrated):

INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.

Create a login user (only needed once — the database has no default
user):

PYTHONPATH=. python -m scripts.create_test_user --username testadmin --password TestPass123! --role admin

Expected output:

username: testadmin
password: TestPass123!
role:     admin

==================================================
SECTION 5
Backend API
==================================================

Exact command:

uvicorn apps.api.app.main:create_app --factory --reload

Expected startup log:

INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
{"asctime": "...", "levelname": "INFO", "name": "apps.api.app.main", "message": "radar-eye-api starting", "environment": "development"}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)

If instead you see "address already in use", port 8000 is already
occupied — see Section 1's process check.

Leave this terminal open?

YES.

==================================================
SECTION 6
DeepStream Runtime
==================================================

Open a SECOND terminal.

cd /home/dev/Documents/Army/Radar-Eye
source .venv/bin/activate
set -a
source .env
set +a

Exact command:

python -m apps.deepstream.app.main

Expected startup log:

{"asctime": "...", "levelname": "INFO", "name": "__main__", "message": "radar-eye-deepstream starting", "environment": "development"}
{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "Initial Desired State synchronization: ()"}
{"asctime": "...", "levelname": "INFO", "name": "__main__", "message": "radar-eye-deepstream running"}

("Initial Desired State synchronization: ()" with empty parentheses means
no camera is registered/OPERATIONAL yet — expected on a clean database.
NVIDIA engine-loading lines print separately, on stderr, between these
two log lines, and take several seconds.)

How do I know Runtime is healthy?

Every 2 seconds this terminal prints two lines:

{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "DeepStream performance snapshot: PerformanceSnapshot(...)"}
{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "Camera Runtime telemetry snapshot: TelemetrySnapshot(liveness=LivenessState(process_alive=True, event_loop_responsive=True, background_workers_alive=True), readiness=ReadinessState(pipeline_ready=True, runtime_supervisor_ready=True, bridge_ready=True, event_bus_ready=True, database_ready=True), ...)"}

Runtime is healthy if every field in ReadinessState reads True and no
"Traceback" or "CRITICAL" line ever appears. Once a camera is registered
and OPERATIONAL (Section 10), inference_fps/pgie_fps/sgie_fps in the
performance snapshot should settle near 24.7.

==================================================
SECTION 7
Frontend
==================================================

Open a THIRD terminal.

cd /home/dev/Documents/Army/Radar-Eye/frontend

Exact command:

bun run dev

Expected output:

VITE v8.0.16  ready in 795 ms

  ➜  Local:   http://localhost:8080/

(If port 8080 is already in use, Vite automatically picks the next free
port and prints that URL instead — use whatever URL actually appears.)

Browser URL:

http://localhost:8080/

==================================================
SECTION 8
Validation Mode
==================================================

Is Validation Mode already enabled?

NO — default is disabled.

Check:

grep -A2 "^production_validation_mode:" configs/validation.yaml

Expected output when disabled:

production_validation_mode:
  enabled: false
  dashboard_interval_seconds: 2.0

If not:

Exactly which file?

configs/validation.yaml

Exactly which line?

Line 45.

Exactly what value must I change?

Change:

  enabled: false

to:

  enabled: true

Then stop and restart the DeepStream Runtime terminal (Section 6) for
the change to take effect — it is only read at process startup.

==================================================
SECTION 9
First Login
==================================================

What page should I see?

The Sign In page, titled "SENTINEL C2". Two fields: Username, Password.

Log in with:

Username: testadmin
Password: TestPass123!

What should already be visible?

After login, the "Live Monitoring" page (the default landing route).
Left-side navigation with these entries: Live Monitoring, Tactical Map,
Cameras, Incidents, Threat Review, Calibration, Evidence, AI Analytics,
System Health, Configuration.

What should NOT yet be visible?

No cameras in "Open Incidents" / "Active Threats" panels (empty — no
camera registered yet). On the Cameras page: "No cameras registered."
(empty state) until Section 10 is completed.

==================================================
SECTION 10
Manual Test Sequence
==================================================

The Cameras screen in this build only supports viewing/editing
Name/Location for a camera that already exists — it has no "Add Camera"
button, and no control for AI enable/disable or lifecycle state. Those
three actions are done with curl against the Backend API terminal in
Section 5, using the same login credential. The DeepStream Runtime
terminal (Section 6) and the dashboard (Section 8) are where you confirm
each action actually took effect.

1.
Get a login token.

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login -H "Content-Type: application/json" -d '{"username":"testadmin","password":"TestPass123!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
echo "token length: ${#TOKEN}"

Expected result:

token length: 229

2.
Register a camera. Replace the rtsp_url/username/password with your real
camera's values.

curl -s -X POST http://127.0.0.1:8000/cameras -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"gate-camera-01","location":"Front Gate","rtsp_url":"rtsp://192.168.68.10:554/Streaming/Channels/101","username":"admin","password":"REPLACE_ME","transport":"tcp"}'

Expected result:

JSON response with "success":true and "lifecycle_state":"DRAFT".
Reload the Cameras page in the browser — the camera now appears in the
list (name, location, status DISCONNECTED).

Save the camera_id from the response for the next steps:

CAMERA_ID="<paste camera_id from the response here>"

3.
Advance the camera through the lifecycle to OPERATIONAL. This is a
three-step state machine — DRAFT can only go to TESTING, TESTING can
only go to VERIFIED or back to DRAFT, VERIFIED can only go to
OPERATIONAL. Attempting to jump straight to OPERATIONAL fails.

curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID/lifecycle" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_state":"TESTING"}'
curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID/lifecycle" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_state":"VERIFIED"}'
curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID/lifecycle" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_state":"OPERATIONAL"}'

Expected result:

Each response has "success":true and the matching "lifecycle_state".
Within 1 second, the DeepStream Runtime terminal (Section 6) prints:

{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "Desired State synchronization: ('add_source:<camera_id>',)"}

If Validation Mode is on (Section 8), the dashboard's Camera/RTSP rows
change from "✗ STALLED" to "✓ Alive".

4.
Enable AI.

curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"ai_enabled":true}'

Expected result:

Response has "ai_enabled":true. Within 1 second, the DeepStream Runtime
terminal prints:

{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "Desired State synchronization: ('enable_ai:<camera_id>',)"}

5.
Disable AI.

curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"ai_enabled":false}'

Expected result:

Response has "ai_enabled":false. DeepStream Runtime terminal prints:

{"asctime": "...", "levelname": "INFO", "name": "apps.deepstream.app.runtime", "message": "Desired State synchronization: ('disable_ai:<camera_id>',)"}

6.
Re-enable AI (needed for the remaining steps).

curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"ai_enabled":true}'

Expected result:

Same as step 4.

7.
Take the camera out of service, then back in.

curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID/lifecycle" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_state":"MAINTENANCE"}'
curl -s -X PATCH "http://127.0.0.1:8000/cameras/$CAMERA_ID/lifecycle" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_state":"OPERATIONAL"}'

Expected result:

DeepStream Runtime terminal prints, in order:

{"asctime": "...", "message": "Desired State synchronization: ('remove_source:<camera_id>',)"}
{"asctime": "...", "message": "Desired State synchronization: ('add_source:<camera_id>', 'enable_ai:<camera_id>')"}

No Traceback, no CRITICAL line, no gap in the periodic performance
snapshot lines before/after. This is the exact operation the
remove_source() pad-lifecycle fix targets — a crash here is a real
regression, not a flake.

8.
Point a real object matching your test scenario at the camera.

Expected result:

DeepStream Runtime terminal (with Validation Mode on, Section 8) prints
the full trace chain for that frame:

{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] FRAME RECEIVED"}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] OBJECT DETECTED class=... conf=... bbox=..."}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] TRACK UPDATED track_id=..."}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] SECONDARY CLASSIFICATION label=..."}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] FRAME OBSERVATION CREATED detections=..."}

If the camera has been calibrated (Calibration page in the browser), it
continues with:

{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] CALIBRATION RESULT zone=... distance=...m"}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] THREAT ASSESSMENT level=..."}
{"asctime": "...", "name": "radar_eye.trace", "message": "[<camera_id>:<frame_num>] EVENT PUBLISHED ThreatAssessmentEvent"}

9.
In the browser, open Incidents and Threat Review.

Expected result:

For a MEDIUM/HIGH/HUMAN_REVIEW assessment from step 8, a matching row
appears.

10.
In the browser, open System Health.

Expected result:

Backend/DeepStream health status shown (this page reads
GET /health/system, /health/gpu, /health/storage, /health/recording — it
does not read the terminal dashboard from Section 6, they are two
independent views of the same underlying state; its Event Log Stream
panel is disabled — "awaiting a GET /audit-log endpoint" — not a defect
in this run).

Continue until the entire application has been validated.

==================================================
SECTION 11
Logs
==================================================

Where are logs?

Nowhere on disk by default — everything prints to the terminal you
started each process in (stdout for application/JSON logs, stderr for
the Validation Mode dashboard and native NVIDIA plugin messages). There
is no log file unless you redirect one yourself.

How do I watch logs live?

Exact commands.

To keep a copy while still watching it live, redirect when you start the
process instead of after:

python -m apps.deepstream.app.main 2>&1 | tee deepstream.log

In a separate terminal, to watch only one subsystem:

tail -f deepstream.log | grep '"name": "radar_eye.stage.pgie"'

To watch only the frame trace:

tail -f deepstream.log | grep '"name": "radar_eye.trace"'

To watch only operator-facing audit events (camera connect/disconnect,
threats, incidents, alarms, watchdog warnings):

tail -f deepstream.log | grep '"name": "radar_eye.audit"'

How do I increase log level?

For everything at once: Section 8 (Validation Mode) sets every
subsystem to DEBUG.

For one subsystem only, edit configs/logging.yaml — e.g. to raise just
pgie:

sed -i 's/^  pgie: INFO/  pgie: DEBUG/' configs/logging.yaml

Restart the DeepStream Runtime terminal for it to take effect.

How do I return to INFO?

sed -i 's/^  pgie: DEBUG/  pgie: INFO/' configs/logging.yaml

Or, if Validation Mode (Section 8) was turned on, set
configs/validation.yaml line 45 back to `enabled: false` and restart.

==================================================
SECTION 12
Shutdown
==================================================

Exactly how do I stop:

API

In the Section 5 terminal: Ctrl+C

DeepStream

In the Section 6 terminal: Ctrl+C

Expected shutdown log:

{"asctime": "...", "message": "radar-eye-deepstream shutting down"}
[NvMultiObjectTracker] De-initialized
{"asctime": "...", "name": "services.incident_service.alarm", "message": "Executing AlarmService fail-safe shutdown..."}

Frontend

In the Section 7 terminal: Ctrl+C

Database (if required)

Not started or stopped by this project — PostgreSQL is assumed to be a
system service already running independently. Do not stop it unless you
know it's safe to for other things on this machine.

Anything else.

Confirm nothing is left running:

pgrep -af "uvicorn|apps.deepstream.app.main|vite dev"

Expected output:

(empty)

If Validation Mode (Section 8) was turned on for this session, set
configs/validation.yaml line 45 back to `enabled: false` before the next
normal run.
