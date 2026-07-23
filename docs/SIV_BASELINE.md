# RM-11.SIV — Performance Baseline

Durable record of measured pipeline performance at each camera count, sourced
from real `siv_reports/*.json` runs (never estimated or interpolated). This
is the reference table the roadmap's 1 → 2 → 4 → 8 → 10 → 20-camera scaling
comparisons (RM-11 Phase 3 and beyond) diff future runs against.

Distinct from:
- `docs/SIV_VALIDATION_REPORT.md` — the PASS/FAIL/Evidence checklist for one
  specific run.
- `siv_reports/siv_report_latest.json` — the raw machine-generated data for
  the most recent run (gitignored, not committed — this file is the
  durable, human-curated summary of what that data showed).
- `docs/BENCHMARK_ACCEPTANCE_CRITERIA.md`/`docs/BENCHMARK_PLAN.md` — formal
  acceptance thresholds for the *approved production* models (RM-15). This
  file tracks pipeline mechanics (fps/latency/GPU) under whatever model is
  currently configured — placeholder or real — not model accuracy.

**How to add a row:** after a `scripts/run_siv.py` session, copy the
relevant fields from that run's `siv_reports/siv_report_*.json` into a new
row below. Never overwrite a prior row — this is an append-only log, same
convention as `docs/IMPLEMENTATION_STATUS.md`'s Recently Completed section.

---

## Scaling Table

| Cameras | Date | Model | Pipeline FPS | PGIE FPS | SGIE FPS | Latency (ms) | GPU Util | GPU Mem | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-07-23 | Placeholder (`resnet18_trafficcamnet` / `resnet18_vehicletypenet`) | 25.9 | 15.8 | 25.8 | 96–110 | 14–40% | 1.2 GB / 12 GB | Baseline established |
| 2 | — | — | — | — | — | — | — | — | Not yet run |
| 4 | — | — | — | — | — | — | — | — | Not yet run |
| 8 | — | — | — | — | — | — | — | — | Not yet run |
| 10 | — | — | — | — | — | — | — | — | Not yet run |
| 20 | — | — | — | — | — | — | — | — | Not yet run |

---

## 1-Camera Baseline Detail (2026-07-23)

Source: RM-11.SIV hardware verification, `feature/RM-11-SIV` (see
`docs/SIV_VALIDATION_REPORT.md` and `docs/IMPLEMENTATION_STATUS.md`'s
Design note (RM-11, SIV)).

| Field | Value |
|---|---|
| Hardware | NVIDIA GeForce RTX 3060 (12 GB), DeepStream 7.0, TensorRT 8.6.1, CUDA 12.2 |
| Camera source | Local `GstRtspServer` test source (`sample_qHD.mp4`, 25fps) — **not a physical camera**, see `docs/SIV_VALIDATION_REPORT.md`'s Known Constraints |
| PGIE model | Placeholder — `resnet18_trafficcamnet` (`pgie.enabled: false`) |
| SGIE model | Placeholder — `resnet18_vehicletypenet` (`sgie.enabled: false`) |
| Pipeline FPS | 25.9 (matches source video's native 25fps — the pipeline is not the bottleneck at 1 camera) |
| PGIE FPS | 15.8 |
| SGIE FPS | 25.8 |
| End-to-end latency | 96–110ms (rolling average; run-to-run variance observed, both figures from real hardware runs) |
| GPU utilization | 14–40% |
| GPU memory | 1.2 GB / 12 GB |
| System memory | ~38% |
| CPU utilization | Not measured (requires two `/proc/stat` samples across `metrics_sample_interval_seconds`; the verification session's runs were shorter than one sample interval) |

**This is a placeholder-model baseline, not a production-model baseline.**
Once the real weapon/uniform models (`docs/MODEL_REGISTRY.md`) are
benchmarked and approved, a second 1-camera row should be added under a
new date reflecting real-model throughput — expect materially different
numbers (a custom-trained detector with a GPU-side custom parser plugin,
see `apps/deepstream/native/README.md`, is not directly comparable to a
stock ResNet18 sample detector). Do not treat this baseline as a
production capacity estimate — see `docs/IMPLEMENTATION_ROADMAP.md`'s
RM-11 risk note on 20-camera Jetson sizing being unmeasured.

---

## Changelog

| Date | Change |
|---|---|
| 2026-07-23 | Initial version. Records the 1-camera placeholder-model baseline from RM-11.SIV's hardware verification. |
