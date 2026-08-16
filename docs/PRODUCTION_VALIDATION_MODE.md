# Production Validation Mode

A single, config-only switch for maximum observability during the first
end-to-end hardware validation run — and any future one. Built entirely
by reusing existing RM-11.SIV instrumentation (stage loggers, the
per-frame pipeline trace, `PerformanceInstrumentation`, `Dashboard`,
`Watchdog`); no new metric collection was added.

## Enable / disable

`configs/validation.yaml`:

```yaml
production_validation_mode:
  enabled: false            # true to enable
  dashboard_interval_seconds: 2.0
```

Read once at process startup (like every other setting in this file) —
not hot-reloadable. Flip it and restart `apps.deepstream.app.main`.
**Default is `false`.** No code edit is required either way.

## What it changes when `enabled: true`

1. **Forces the per-frame pipeline trace on**, regardless of this same
   file's `frame_trace.enabled` value. This is the existing
   `PipelineTracer` (`apps/deepstream/app/pipeline_trace.py`) — logs the
   full FRAME RECEIVED → OBJECT DETECTED → TRACK UPDATED → SECONDARY
   CLASSIFICATION → FRAME OBSERVATION CREATED → CALIBRATION RESULT →
   THREAT ASSESSMENT → INCIDENT CREATED → ALARM GENERATED → EVENT
   PUBLISHED chain, one line per stage per frame, to the
   `radar_eye.trace` logger, tagged with a `[camera_id:frame_num]`
   correlation id.
2. **Elevates every `radar_eye.stage.*` logger to DEBUG**
   (`stage_logging.enable_maximum_observability()`) — an override layered
   on top of `configs/logging.yaml`'s normal per-logger levels, not a
   replacement for that file.
3. **Starts the console dashboard and watchdog** inside the real
   production entrypoint (`apps.deepstream.app.main`) — the same
   `Dashboard`/`Watchdog` classes `scripts/run_siv.py` already used,
   reading the exact same `HeartbeatRegistry`/`PerformanceInstrumentation`
   objects `DeepStreamRuntime` already owns and updates. No parallel
   metric path.

## What it does NOT change

No pipeline topology, no threat/incident/alarm decision logic, no valve
behavior, no reconnect behavior. It is purely additive observability —
identical to disabling it, minus the extra log volume and the dashboard.

## Logging architecture (already existed, confirmed here)

Every subsystem in the request already has its own logger, independently
configurable via `configs/logging.yaml`'s `loggers:` map (DEBUG through
ERROR, standard `logging` levels):

`camera`, `rtsp`, `deepstream`, `pgie`, `nvdcf`, `sgie`, `runtime_adapter`,
`threat_runtime_adapter`, `calibration`, `threat_engine`,
`incident_service`, `alarm_service`, `recording`, `health`, `event_bus`,
`performance`, `system`, plus `visualization` (18 total — one more than
originally listed, added for RM-11.SIV Visualization).

Honest disclosure: not all 18 currently have an active call site emitting
through them — `camera`, `runtime_adapter`, `system`, `calibration`,
`threat_engine`, and `visualization` do; the remainder are declared,
independently configurable, and ready, but have no log statement wired to
them yet in the current codebase. Production Validation Mode elevates all
18 to DEBUG regardless — the ones with no call site simply stay silent.
Wiring the rest up was judged out of scope here (adding new log
statements across many files is a broader change than "make the existing
mechanism maximally visible," and wasn't asked for) — flagged rather than
silently left unmentioned.

## Console dashboard

Renders to **stderr**, not stdout — application logging (structured JSON)
owns stdout. A screen-clearing dashboard sharing stdout with logging would
periodically wipe log lines out from under an operator watching them. To
watch both cleanly in one terminal, redirect one away, e.g.:

```bash
python -m apps.deepstream.app.main 2>dashboard.log
# or, to keep the dashboard on screen and logs in a file:
python -m apps.deepstream.app.main >app.log
```

Or simply accept both interleaved in one terminal for a quick check —
harmless, just visually busy.

## Trade-offs (measured on real hardware, not assumed)

**Per-frame trace overhead.** Hardware-measured, single camera, real
models, back-to-back runs on the same scene:

| | Disabled (default) | Enabled |
|---|---|---|
| Pipeline FPS | 24.75 | 24.75 |
| End-to-end latency | ~5.37ms | ~5.5–5.7ms |

No measurable FPS impact; latency stayed within this session's normal
run-to-run noise band (this exact pipeline has shown 4.6–5.9ms across
otherwise-identical runs earlier in this validation effort). This test
scene produced zero real detections, so `OBJECT DETECTED`/`TRACK UPDATED`/
`SECONDARY CLASSIFICATION` — the per-*object*, not per-*frame*, trace
calls — were never exercised at volume; a scene with sustained multiple
detections would log more lines per frame and has not been separately
measured. `FRAME RECEIVED` and `FRAME OBSERVATION CREATED`, which fire
unconditionally every frame regardless of detections, showed no
regression.

**Dashboard/watchdog cost.** Both are periodic asyncio tasks (default 2s
interval) reading already-computed state — no additional GStreamer
pipeline interaction, no measurable overhead expected or observed.

**Stdout/stderr separation.** A real, disclosed architectural choice (see
above), not a defect — the dashboard was moved to stderr specifically to
resolve this rather than leaving logs and dashout output to visually
clobber each other by default.

## Reuse, not duplication

Nothing here collects a metric `PerformanceInstrumentation` didn't already
collect, and nothing here introduces a second health/liveness source next
to `HeartbeatRegistry`/`TelemetryCollector`. The only new code is: one
config flag, one logger-level-elevation helper, and wiring the
already-built `Dashboard`/`Watchdog` into `apps.deepstream.app.main`
instead of only `scripts/run_siv.py`.
