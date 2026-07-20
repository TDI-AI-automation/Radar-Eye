# Implementation Roadmap

## Authority

This document is the single source of truth for **milestone sequencing** — what gets built, in what order, and why. It supersedes any other RM-numbered milestone list in this repository, including the one previously embedded in `IMPLEMENTATION_STATUS.md` (which was sourced from `docs/TASKS.md`'s `RE-xxx` ranges and reused the same `RM-XX` IDs to mean different work — that table has been replaced; see `IMPLEMENTATION_STATUS.md`'s changelog).

This document does **not** govern:

- **Ticket-level backlog, acceptance criteria per ticket, or blockers** — that remains `TASKS.md` (root), whose format is still under review.
- **Which Git branch owns which subsystem, or current build status** — that is `IMPLEMENTATION_STATUS.md`'s Subsystem Status table.
- **Branching and merge mechanics** — that is `CLAUDE.md`'s "Git Branching & Merge Strategy" section and `PROJECT_CONTEXT.md`'s "# Repository" section.

Milestones (`RM-XX`) are a planning and sequencing concept only. They are never Git branch names.

---

## Milestone Sequence

| ID | Milestone | Status | Depends On | Complexity |
|---|---|---|---|---|
| RM-01 | Repository & Runtime Foundation | **Done** | None | Low |
| RM-02 | Shared Contracts Package | Not Started | RM-01 | Low-Medium |
| RM-DEV | Developer Infrastructure | Not Started | RM-02 | Low-Medium |
| RM-06 | Threat Engine Service | Not Started | RM-02 | Medium |
| RM-03 | Database Migrations & Persistence Layer | Not Started | RM-01, RM-02 | Medium |
| RM-04 | Internal Event Bus | Not Started | RM-01, RM-02 | Medium |
| RM-07 | Incident Service | Not Started | RM-02, RM-03, RM-04, RM-06 | Medium |
| RM-05 | Calibration Service | Not Started | RM-02, RM-03 | Medium |
| RM-08 | Recording & Evidence Service | Not Started | RM-02, RM-03, RM-04, RM-07 | Medium-High |
| RM-09 | Health & Monitoring (lightweight) | Not Started | RM-02, RM-03, RM-04 | Low-Medium |
| RM-10 | Alarm Service | Not Started | RM-02, RM-04, RM-06 | Medium |
| RM-11 | DeepStream AI Pipeline | Not Started | RM-01, RM-02, RM-04, RM-05, RM-06 | Very High |
| RM-12 | API Service (REST + WebSocket) | Not Started | RM-02, RM-03, RM-04 | Medium-High |
| RM-13 | Frontend Integration | Not Started | RM-12 (contract-parallel) | Medium |
| RM-14 | Jetson Deployment & Packaging | Not Started | RM-01–RM-11 substantially complete | High |
| RM-15 | End-to-End Validation & Benchmarking | Not Started | RM-14 | High |

Order reflects dependency and priority sequencing, not a strict gate. Under the subsystem-branch model, milestones living on different subsystem branches can proceed in parallel per available capacity (human or AI-assistant). This table states what to prioritize when a choice exists, not a rule that, say, RM-07 cannot start before RM-05 finishes.

---

## Milestone Detail

### RM-01 — Repository & Runtime Foundation — Done
FastAPI app factory, settings loading (YAML + environment-only secrets), structured JSON logging (`python-json-logger`), async SQLAlchemy engine/session factory. No application routes. Implemented, tested, merged into `feature/api`.

### RM-02 — Shared Contracts Package
**Deliverables:** `shared/events` (envelope + payload models per `EVENT_CONTRACTS.md`), `shared/schemas` (API models per `FRONTEND_BACKEND_CONTRACTS.md`), `shared/constants` (threat levels, distance zones, weapon taxonomy, uniform classes).
**Acceptance:** every event type in `EVENT_CONTRACTS.md` has a matching schema; no service defines its own duplicate enum.
**Testing:** schema round-trip unit tests; a check against duplicate enum definitions.

### RM-DEV — Developer Infrastructure
**Deliverables:** formatting, linting, pre-commit hooks, CI pipeline, repository quality gates, formalized pytest conventions building on RM-01's minimal baseline.
**Acceptance:** CI runs on every PR; pre-commit blocks obviously-broken commits; formatting/linting apply repo-wide.
**Testing:** the tooling is validated by running it against RM-01's existing code.

### RM-06 — Threat Engine Service
**Deliverables:** `services/threat_engine` — the deterministic rule table from `THREAT_ENGINE_SPEC.md`, escalation timers (3-frame HIGH → event, 1s → incident, 3s → alarm; 2s MEDIUM → incident; FIRE immediate), de-escalation timers (10s/5s/3s).
**Acceptance:** 100% rule consistency against every row of the spec's table; every emitted `ThreatAssessmentEvent` carries `rule_id`.
**Testing:** exhaustive unit tests over the full rule table — buildable and testable with synthetic inputs, independent of any AI pipeline.

### RM-03 — Database Migrations & Persistence Layer
**Deliverables:** Alembic migrations implementing every `DATABASE_SCHEMA.md` table; RTSP credential encryption at rest; indices on hot query paths.
**Acceptance:** schema matches `DATABASE_SCHEMA.md` field-for-field; migrations reversible; `(camera_id, track_id)` active-incident uniqueness enforced.
**Testing:** migration up/down tests; a DB-level test asserting the dedup constraint rejects a second active incident.

### RM-04 — Internal Event Bus
**Deliverables:** the producer→event→consumer transport mandated by ADR-007, implementing `EVENT_CONTRACTS.md`'s envelope and versioning rules.
**Acceptance:** every service publishes/subscribes using only `shared/events` types; events immutable once published.
**Testing:** pub/sub delivery unit tests; a fault-injection test (kill one consumer, confirm others unaffected).
**Note:** the concrete transport mechanism is an implementation-time engineering choice, not an architecture decision.

### RM-07 — Incident Service
**Deliverables:** `services/incident_service` — dedup enforcement, state machine per `INCIDENT_LIFECYCLE.md`.
**Acceptance:** a `ThreatAssessmentEvent` stream for one track produces exactly one incident, never duplicates; 10s track-lost auto-close.
**Testing:** integration test simulating rapid repeated events for the same track.

### RM-05 — Calibration Service
**Deliverables:** `services/calibration` — homography computation, ground-plane distance/zone calculation, `CalibrationUpdatedEvent`.
**Acceptance:** distance error ≤2m @20m, ≤5m @50m per `BENCHMARK_ACCEPTANCE_CRITERIA.md`.
**Testing:** unit tests on synthetic reference points; physical validation once cameras are mounted.

### RM-08 — Recording & Evidence Service
**Deliverables:** `services/recording` — event-clip generation (10s pre / 20s post buffer), snapshots, storage-quota eviction. **Retention policy remains ADR-017 as documented (continuous recording, 30-day retention) — no reduced-window policy is implemented.** The retention duration must be a **configurable value, isolated from the recording logic itself**, so a future policy change — if benchmarking ever shows ADR-017 infeasible — doesn't require re-architecting the service.
**Acceptance:** every incident produces exactly one snapshot + one clip; disk-full raises a health alert before it stops ingest; retention duration is a single, isolated configuration value.
**Testing:** clip-timing accuracy test; storage-pressure test.

### RM-09 — Health & Monitoring (lightweight)
**Deliverables:** minimal health/monitoring surfaced from inside `apps/api` — GPU/storage/service/camera status. **No dedicated `services/health_service` package.** If implementation demonstrates a real need for one, stop and request approval before creating it.
**Acceptance:** per-camera connected/FPS/last-frame-age visible; a stalled-but-alive pipeline is detected.
**Testing:** threshold-logic unit tests; a fault-injection test for a stalled (not crashed) stream.

### RM-10 — Alarm Service
**Deliverables:** hardware-agnostic alarm integration per ADR-012, consuming `AlarmRequestedEvent`, HIGH/FIRE-only per ADR-026. **Implemented under `feature/incident-service`** — not a separate subsystem — until implementation demonstrates it's large enough to warrant its own branch.
**Acceptance:** alarm never fires outside HIGH/FIRE; documented fail-safe behavior on process death; manual silence/override always available.
**Testing:** event-filter unit tests; hardware-in-the-loop test once alarm hardware exists.

### RM-11 — DeepStream AI Pipeline
**Deliverables:** `apps/deepstream` — RTSP ingestion with reconnect handling, PGIE (YOLO26M/TensorRT), NvDCF tracker, SGIE (ViT/TensorRT, binary+threshold), in-process calls into RM-06 and RM-05, decision events onto RM-04's bus.
**Acceptance:** 20 cameras concurrently on one Jetson; detector ≥90% precision/recall, ≤5 false positives/hour/camera; 2h soak with no memory growth.
**Testing:** per-component benchmark before full integration; physical cable-pull reconnect test.
**Risk:** highest-complexity milestone in the project — no prior benchmark data exists for 20-camera single-Jetson throughput. An early partial-capacity spike is recommended before committing to the full integration timeline.

### RM-12 — API Service (REST + WebSocket)
**Deliverables:** every endpoint/channel in `FRONTEND_BACKEND_CONTRACTS.md`; auth + audit (both inside `apps/api`, per the accepted Auth/Audit/Monitoring decision); bridges the event bus to WebSocket.
**Acceptance:** contract-tested against `FRONTEND_BACKEND_CONTRACTS.md`; alert latency ≤2s; role-gated routes enforced.
**Testing:** contract tests; WebSocket end-to-end latency test.

### RM-13 — Frontend Integration
**Deliverables:** replace `radar-eye-command`'s mock data; threat-level presentation redesign (ALLY/OBSERVE/LOW/MEDIUM/HIGH); Threat Review Center, Calibration Center, Evidence Viewer screens; Jetson-specific health widgets.
**Acceptance:** zero remaining `mock-data.ts` references; every `UI_SCREEN_CATALOG.md` screen present.
**Testing:** component tests for new screens; end-to-end golden-path test.

### RM-14 — Jetson Deployment & Packaging
**Deliverables:** offline-installable bundle; systemd units; on-device TensorRT engine builds (FP16/INT8); power/thermal validation.
**Acceptance:** installs on a fresh Jetson with networking disabled; survives a cold power-cut; zero thermal throttle over a 4h soak (or a documented throttled-FPS figure).
**Testing:** wiped-device install test; cold power-cut test; 4h thermal soak.

### RM-15 — End-to-End Validation & Benchmarking
**Deliverables:** execution of `BENCHMARK_PLAN.md` / `BENCHMARK_ACCEPTANCE_CRITERIA.md` for real, on real hardware; 24h continuous soak.
**Acceptance:** every numeric threshold met, or an explicit documented gap with a mitigation plan; 24h soak with zero crashes, flat memory.
**Testing:** this milestone *is* the testing.

---

## Changelog

| Date | Change |
|---|---|
| 2026-07-19 | Initial version. Consolidates the roadmap agreed during planning, reordered per approved guidance (RM-06 moved earlier; Developer Infrastructure inserted after RM-02; RM-10 assigned to `feature/incident-service` rather than a new subsystem). Supersedes the RM-numbered table previously embedded in `IMPLEMENTATION_STATUS.md`. |
