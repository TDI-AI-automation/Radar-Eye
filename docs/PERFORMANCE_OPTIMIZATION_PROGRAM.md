# Performance Optimization Program

**Status:** Program definition. No optimization work has begun under this
program as of this document's creation.

**Relationship to other documents:** This is a cross-cutting engineering
workstream definition, not a roadmap milestone. It does not redefine, rename,
or supersede any `RM-XX` entry in `docs/IMPLEMENTATION_ROADMAP.md` — that
document remains the sole authority for milestone sequencing and
definitions, per `CLAUDE.md`'s priority order. This program runs alongside
the roadmap, not inside it.

---

## 1. Purpose

Implementation milestones (`RM-XX`) exist to deliver and validate product
functionality against defined acceptance criteria — a milestone is "done"
when its scope works correctly, not when it is fast. Performance and
accuracy optimization is a different kind of work: it has no natural
completion point tied to a single feature, it benefits from being measured
against a stable, already-validated baseline rather than a moving target,
and it carries a real risk of introducing functional regressions if pursued
inside the same change as new feature work.

Separating optimization into its own program keeps these concerns from
interfering with each other in both directions: feature milestones are not
delayed by premature tuning, and optimization work is not scoped or
rushed to fit inside an unrelated milestone's boundaries. This is
consistent with the principle already established for RM-11 itself
(`docs/IMPLEMENTATION_STATUS.md`, Design note (RM-11)): *"infrastructure
first, integration second, optimization last — no throughput optimization
before single-camera correctness is verified."* This program is that same
principle, generalized: optimization begins only once there is a validated
baseline to optimize against, and proceeds independently of whichever
roadmap milestone is concurrently in progress.

Optimization work under this program may occur alongside future roadmap
milestones where appropriate (e.g., a Priority 1 reliability fix identified
during RM-11.SIV may be implemented while RM-12 is also in progress), but
it is tracked, measured, and reviewed under this program's own rules, not
under a milestone's acceptance criteria.

---

## 2. Baseline

The RM-11 Development System Integration Validation (Development SIV)
establishes the baseline against which all future optimization work under
this program is measured. Source artifacts:

- `artifacts/RM-11.SIV-FINAL-VALIDATION/` — logs, GPU metrics, screenshots,
  and reports from the RM-11.SIV validation session (2026-07-23).
- `docs/RM-11_SIV_ENGINEERING_REVIEW.md` — the audit of that session's
  evidence, including the Known Issues this program's early work should
  address.
- `docs/SIV_BASELINE.md` — the durable, append-only performance baseline
  log, including the Visualization OFF vs. ON comparison.

Baseline figures recorded from the RM-11.SIV session (real hardware, real
production models, real camera, RTX 3060 12GB — see
`docs/RM-11_SIV_ENGINEERING_REVIEW.md`'s GPU Review and Log Review sections
for full detail):

| Metric | Baseline value |
|---|---|
| Inference FPS (steady-state) | ~24.5–24.8 |
| End-to-end latency (steady-state) | 4.4–5.9 ms |
| Visualization FPS | ~24.5–29.4 (tracks inference FPS) |
| Overlay render time | 0.055–0.165 ms |
| GPU utilization | 9.0–34.0%, average 18.0% |
| GPU memory used | 2176–2755 MB (of 12,288 MB) |
| GPU temperature | 51–62°C |
| GPU power draw | 48.8–66.1 W |
| Pipeline startup time | 12.1–13.1 s (cached TensorRT engines) |

This baseline reflects a **single-camera** configuration on **x86/RTX
3060** development hardware, not the Jetson AGX Orin production target and
not a multi-camera configuration — both are explicitly out of this
baseline's scope and are themselves optimization/validation targets under
Multi-camera Scaling (§3) and future Jetson-specific benchmarking
(`docs/IMPLEMENTATION_ROADMAP.md`'s RM-14).

No optimization change may claim an improvement without citing which
baseline figure above (or a documented successor baseline, per the
Engineering Rules in §5) it improved upon.

---

## 3. Optimization Categories

Each category below is a distinct area of future optimization work. Listing
a category here is not a commitment to work on it, nor a claim that it
currently underperforms — it is a scope definition for where future
optimization proposals belong.

| Category | Scope |
|---|---|
| DeepStream Pipeline | Element configuration, buffer/queue tuning, batching, pipeline topology efficiency. |
| TensorRT | Engine precision (FP16/INT8), engine caching/build strategy, batch size tuning. |
| PGIE | Primary detector throughput, confidence/NMS tuning, model-level performance. |
| SGIE | Secondary classifier throughput, batch efficiency, classification confidence tuning. |
| Tracker | NvDCF tuning, track stability, ID-switch reduction. |
| Visualization | OSD render cost, encoder settings, overlay efficiency (see `docs/SIV_BASELINE.md`'s OFF vs. ON overhead figures as this category's own baseline). |
| RTSP | Stream delivery efficiency, client-join latency, multi-client scaling. |
| GPU | Overall GPU utilization efficiency across all stages sharing the device. |
| Memory | GPU and system memory footprint, leak detection over long runs. |
| Multi-camera Scaling | Behavior and resource usage as camera count increases toward the 20-camera target (`docs/IMPLEMENTATION_ROADMAP.md`'s RM-11 Phase 3 scope). |
| Detection Accuracy | Precision/recall of the production models once benchmarked and approved (`docs/MODEL_REGISTRY.md`) — distinct from pipeline mechanics. |
| System Reliability | General robustness of the running system under real operating conditions. |
| Startup Robustness | Process startup behavior under adverse conditions — directly informed by `docs/RM-11_SIV_ENGINEERING_REVIEW.md`'s Known Issue #2. |
| Database Resilience | Database connectivity/availability handling, including startup and runtime retry/backoff behavior — directly informed by Known Issue #2. |

**Recorded finding (PR #8 code review, forward-looking, not blocking RM-11):**
Visualization UDP port allocation must become configurable before
multi-camera support. `apps/deepstream/app/visualization/pipeline_builder.py`'s
`_INTERNAL_UDP_PORT` is a single fixed constant (5400), correct for RM-11.SIV's
single-camera scope but a collision risk once multiple cameras' visualization
branches run in the same process (Multi-camera Scaling, above). No
implementation or configuration change made under RM-11 — recorded here only,
to be picked up as part of Multi-camera Scaling / Visualization work under
this program.

---

## 4. Benchmark Targets

Placeholders only — no target values are set by this document. Targets
must be proposed, justified, and agreed before any optimization work
against them begins, per the Engineering Rules in §5. The Baseline column
below is filled from §2 where a session figure exists; where no session
figure exists, the metric is listed for future benchmarking to establish
its own baseline before a target is set.

| Metric | Baseline (RM-11.SIV) | Target | Notes |
|---|---|---|---|
| FPS | ~24.5–24.8 (single camera, x86/RTX 3060) | TBD | Multi-camera and Jetson targets require their own baseline runs first. |
| Latency | 4.4–5.9 ms (single camera, x86/RTX 3060) | TBD | — |
| GPU Utilization | 9.0–34.0%, avg 18.0% (single camera) | TBD | Expected to scale with camera count; no multi-camera figure exists yet. |
| Memory | 2176–2755 MB GPU (single camera) | TBD | System (RAM) memory not separately baselined this session. |
| Precision | Not measured this session | TBD | Blocked on `docs/MODEL_REGISTRY.md` model benchmarking/approval. |
| Recall | Not measured this session | TBD | Blocked on `docs/MODEL_REGISTRY.md` model benchmarking/approval. |
| Tracker Stability | Not formally measured this session (qualitative: stable track IDs observed, e.g. `ID #62`, `ID #269`) | TBD | Needs a defined metric (e.g. ID-switch rate) before a target is meaningful. |
| Throughput | 89,850 combined frames processed across the RM-11.SIV session, zero drops observed | TBD | — |

---

## 5. Engineering Rules

These rules govern all work performed under this program, without
exception:

1. **Every optimization must have before/after measurements.** A change is
   not "an optimization" until it is measured against the relevant
   baseline metric from §2/§4 (or a documented successor baseline) both
   before and after the change.
2. **No optimization without reproducible benchmarks.** The exact
   configuration, hardware, camera count, and measurement method used must
   be recorded (following the pattern already established in
   `docs/SIV_BASELINE.md`) so the result can be independently reproduced,
   not just cited.
3. **Functional regressions are unacceptable.** An optimization that
   improves a benchmarked metric while breaking or degrading correctness,
   test coverage, or any behavior validated in `docs/RM-11_SIV_ENGINEERING_
   REVIEW.md` is not an acceptable optimization, regardless of the
   performance gain.
4. **Changes require rollback capability.** Every optimization change must
   be revertible independently (its own commit, its own config flag where
   applicable) — never bundled with unrelated changes in a way that
   forecloses reverting just the optimization if it proves harmful.
5. **Optimize only against the RM-11 baseline** (§2) or a later baseline
   explicitly recorded under this program — never against an assumed,
   estimated, or undocumented starting point.

All other repository-wide engineering discipline continues to apply
unchanged: standard branching/review/merge rules (`CLAUDE.md`'s Git
Branching & Merge Strategy), quality gates, and narrow-scope change
discipline. This program adds measurement and baseline discipline on top
of those existing rules — it does not replace them.
