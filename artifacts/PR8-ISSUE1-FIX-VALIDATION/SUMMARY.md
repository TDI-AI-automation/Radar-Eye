# PR #8 Review Fix Validation — Issue #1 (`VisualizationManager.mark_failed()` teardown)

Minimal, targeted re-validation of the fix for the code-review finding on
PR #8 (`VisualizationManager.mark_failed()` didn't tear down a
partially-built visualization branch). Not a repeat of the full RM-11.SIV
validation — see `artifacts/RM-11.SIV-FINAL-VALIDATION/` for that.

**Environment:** same as the RM-11.SIV baseline (NVIDIA RTX 3060 12GB,
DeepStream 7.0.0, real production PGIE/SGIE models, real camera).

**Scenario reproduced:** `configs/visualization.yaml` `enabled: true`,
`rtsp_port: 8554` deliberately pre-bound by another process before
launching `scripts.run_siv` — forces `RtspStreamServer.start()` to raise,
exercising `VisualizationManager.start()`'s failure path and
`builder.py`'s `mark_failed()` call, the exact code path the fix changed.

**Result — confirmed via `runtime.log` (this directory):**

- Failure reproduced as expected: `"Visualization failed to start --
  continuing without it (inference is unaffected)"` (single log line, full
  traceback — the previously-duplicated status log from `manager.py` no
  longer appears, confirming the Issue #2 fix).
- `health()`'s reported state confirmed correct via
  `"Visualization enabled but not running: Failed to attach RTSP server on
  port 8554 (already in use by another process?)"`.
- No `"Visualization cleanup after failure also raised"` line — the new
  teardown call completed without itself raising.
- **No orphaned visualization branch:** `visualization_fps` and
  `overlay_time_avg_ms` remained `None` in every performance snapshot for
  the rest of the run (verified across 45,000+ additional frames, ~30
  minutes) — before the fix, these continued populating with real numbers
  after a failed start, because the branch kept running.
- **GPU utilization/memory returned to baseline:** stabilized at
  ~1211–1216 MB / ~27–28% utilization — well below the ~2432–2529 MB range
  recorded when visualization is actually running with these same real
  models (`docs/RM-11_SIV_ENGINEERING_REVIEW.md`'s GPU Review). Consistent
  with the branch being torn down, not left running unpublished.
- **Inference unaffected throughout:** Pipeline/Camera/RTSP/PGIE/NvDCF/
  SGIE/RuntimeAdapter/ThreatEngineRuntimeAdapter all remained `✓ Alive` at
  ~24.7 FPS for the full run — failure isolation holds.

**Shutdown:** clean (`SIV report written to
apps/siv_reports/siv_report_2026-07-24T135057.496255+0000.json`).

**Config state:** `configs/models.yaml`/`configs/visualization.yaml`
restored from backup to tracked defaults after this test; no config
changes committed.
