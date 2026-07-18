# Implementation Status

> **What this is:** A live rollup of *build state* — what exists in code today, who is building what, on which branch, and what is blocking them. One row per subsystem, not per task.
>
> **What this is not:** Not architecture (see `ADR_INDEX.md` → `THREAT_ENGINE_SPEC.md` → `EVENT_CONTRACTS.md` → `DATABASE_SCHEMA.md` → `DEEPSTREAM_PIPELINE_SPEC.md` → `FRONTEND_BACKEND_CONTRACTS.md` → `AGENTS.md`, per `CLAUDE.md`'s priority order). Not a ticket backlog — that is `TASKS.md` (root), which owns individual `RE-XXX` tickets, acceptance criteria, and the critical path, and is the authority on what work is currently in scope. This file only tracks the subsystem-level *result* of that backlog: is the code there or not.
>
> **When to update:** Any time a subsystem's status, owner, branch, or blocker changes — in the same PR/commit that causes the change, not on a schedule. Stale rows are worse than missing rows.
>
> **Who updates it:** Whoever changes the state — human or AI assistant. If you merge code that moves a subsystem from `Not Started` to `In Progress`, update its row before you consider the task done. The Orchestrator role (`AGENTS.md`) reconciles this file against `TASKS.md` when they drift.
>
> **Recommended read order when starting work in this repo:**
> `CLAUDE.md` → `PROJECT_CONTEXT.md` → `ADR_INDEX.md` → `TASKS.md` → **this file** → subsystem documentation / code.
> Read `TASKS.md` first because it is the gating source of truth — per its own rule, *no code may be written without a task* — and it defines the scope, ticket IDs, and milestone boundaries this file merely reports against. Read this file second to see how far the currently authorized backlog has actually progressed, without re-deriving that from `git log` or the source tree. Then go to the architecture docs (priority order above) for how a subsystem must be built. Do not infer status from this file alone when the task is destructive or high-stakes — verify against the actual source tree first, since this file can lag reality.

---

## Architecture Contract

- This document tracks **implementation state only** — what is built, in progress, or blocked.
- It is **not** an architecture document and carries no authority over design decisions.
- It must **never** be edited to reflect, justify, or work around a change to architecture — architecture changes belong in an ADR (`ADR_INDEX.md`) per `CLAUDE.md`'s priority order.
- If implementation work conflicts with an architecture document, **implementation stops**. Do not resolve the conflict by editing the architecture doc or by proceeding around it — raise it for clarification (new ADR or human decision) first.

## Source of Truth

This document reflects the **operational implementation state** as last recorded by whoever updated it — it is a report, not a ledger. If it temporarily disagrees with the actual source code (a merged PR that hasn't updated a row yet, a rollback, a branch that moved faster than the doc), **the source code is authoritative** until this document is corrected. When you find a disagreement, fix the row — don't act on the stale status and don't treat the code as wrong because this file says otherwise.

---

## Snapshot

| | |
|---|---|
| Current sprint | v1 delivery — target **2026-07-26** (scope not yet ratified, see `RE-001` in `TASKS.md`) |
| Repo stage | Pre-implementation scaffolding — package directories exist, all contain stub `__init__.py` only |
| Primary branch | `master` (protected — no direct commits per `PROJECT_CONTEXT.md`) |
| Integration branch | `develop` |

---

## Next Immediate Action

**Current Milestone:**
RM-01 — Phase 1: AI (Model Optimization & Selection)

**Status:**
Not Started — blocked.

**Blocking Issues:**
`RE-001` (v1 scope not yet ratified) blocks all work per `TASKS.md`. `RE-006` (DeepStream/JetPack/CUDA version triple unresolved) is a direct dependency of `RE-101`, the ticket that carries this milestone. Resolve both before starting substantive RM-01 work; if either is still open, resolving it is the actual next action.

---

## Roadmap Progress

Single authoritative milestone sequence — sourced from `TASKS.md` §1.1 ("Budget vs. capacity") and §2.3 ("ID ranges"), the dated, Orchestrator-maintained plan the live `RE-XXX` ticket backlog is organized around. `docs/IMPLEMENTATION_PLAN.md`'s earlier 8-phase sketch is superseded by this breakdown for tracking purposes and is retained only as historical/architectural background — do not derive milestones from it.

| Milestone | Phase (`TASKS.md`) | Ticket Range | Description | Status |
|---|---|---|---|---|
| RM-01 | Phase 1 — AI | `RE-1xx` | Model optimization, TensorRT export, final selection, class list freeze | Not Started |
| RM-02 | Phase 2 — Backend & API | `RE-2xx` | FastAPI service, DB schema, MQTT event contract, evidence storage, auth, camera API | Not Started |
| RM-03 | Phase 2 — Frontend | `RE-3xx` | API contract freeze, live camera grid, threat event feed, login/session, health dashboard | Not Started |
| RM-04 | Phase 2 — AI Integration & Scoring | `RE-4xx` | DeepStream pipeline (ingest→PGIE→tracker→SGIE), inference-stream ADR, threat scoring & de-dup, fire tuning | Not Started |
| RM-05 | Phase 2 — Jetson Deployment | `RE-5xx` | Offline deployment bundle, systemd/watchdog, power/thermal validation, model update procedure | Not Started |
| RM-06 | Phase 3 — IoT Device | `RE-6xx` | Relay controller driver, alarm policy engine, beacon control, GPIO stub fallback | Not Started |
| RM-07 | Phase 4 — Evaluation | `RE-7xx` | Frame-drop eval, live-footage accuracy eval, degraded-mode behavior, 24h soak, acceptance & handover | Not Started |

`RE-0xx` (blockers/decisions) and `RE-9xx` (deferred backlog) are cross-cutting and deferred scope respectively — they gate or sit outside this milestone sequence rather than belonging to a single row. See `TASKS.md` §3 and §11.

---

## Subsystem Status

| Subsystem | Path | Status | Owner | Branch | Depends On |
|---|---|---|---|---|---|
| Shared contracts (events, schemas, constants) | `shared/` | Not Started | `@agent-backend` | `feature/backend-foundation` | — |
| API service (FastAPI, REST + WebSocket) | `apps/api/` | Not Started | `@agent-backend` | `feature/backend-foundation` | Shared contracts |
| DeepStream pipeline (ingest → YOLO → NvDCF → ViT) | `apps/deepstream/` | Not Started | `@agent-vision` | `feature/restart-architecture` | Shared contracts |
| Threat engine (rule-based scoring) | `services/threat_engine/` | Not Started | `@agent-vision` | — | DeepStream pipeline, Shared contracts |
| Incident service | `services/incident_service/` | Not Started | `@agent-backend` | — | Threat engine, API service |
| Recording / evidence service | `services/recording/` | Not Started | `@agent-backend` | — | Incident service |
| Camera calibration service | `services/calibration/` | Not Started | `@agent-vision` | — | Shared contracts |
| Frontend (Command Center UI) | external repo: `radar-eye-command` | Prototype UI complete, **not integrated** | `@agent-frontend` | — (separate repo) | API service |
| Deployment bundle / systemd | `deployments/`, `scripts/` | Not Started | `@agent-platform` | — | All backend subsystems |

Status values: `Not Started` · `In Progress` · `Blocked` · `In Review` · `Done`.

---

## Blocked

Subsystem-level blockers only. Full detail, acceptance criteria, and owners live on the referenced ticket in `TASKS.md`.

| Blocks | Ticket | One-line reason |
|---|---|---|
| Everything | `RE-001` | v1 scope for 2026-07-26 not yet ratified |
| DeepStream pipeline sizing | `RE-003` | Jetson compute budget never measured on real hardware |
| API / Incident service schema | `RE-004` | Node topology and data-ownership ADR not yet written |
| Deployment bundle | `RE-006` | DeepStream/JetPack/CUDA version triple unresolved |
| Recording / evidence service | `RE-007` | "30-day retention" storage policy not yet defined |

---

## Recently Completed

| Date | Item |
|---|---|
| 2026-07-16 | Repository skeleton, package structure for `apps/`, `services/`, `shared/` |
| 2026-07-16 | Architecture freeze v2 — priority-ordered spec set in place |
| — | Frontend prototype UI (separate repo, pre-dates this architecture — requires audit) |

---

## Implementation Notes

Running log of build-time findings that future contributors (human or AI) need but that don't belong in an ADR or spec. Newest first. Keep entries short — one or two lines. Move anything that becomes a durable architecture decision into an ADR instead of leaving it here.

- 2026-07-18 — All `apps/*` and `services/*` packages currently contain only `__init__.py`. Treat any subsystem not listed as "In Progress" or later above as literally empty before starting work — do not assume partial implementation exists.

---

## Related Documents

- `TASKS.md` (root) — ticket-level backlog, acceptance criteria, critical path, and the authoritative milestone sequence (`Roadmap Progress` above is sourced from its §1.1/§2.3)
- `docs/IMPLEMENTATION_PLAN.md` — earlier 8-phase sketch, superseded by `TASKS.md` for milestone tracking; kept for historical/architectural background only
- `ADR_INDEX.md` — accepted architecture decisions
- `PROJECT_CONTEXT.md` — static project facts (hardware, repos, stack)
- `AGENTS.md` — agent roster and communication rules

---

## Changelog

| Date | Change | By |
|---|---|---|
| 2026-07-18 | Initial version created | Claude |
| 2026-07-18 | Added Roadmap Progress, Next Immediate Action, and Architecture Contract sections; reordered recommended read sequence to place `TASKS.md` before this file | Claude |
| 2026-07-18 | Re-sourced Roadmap Progress from `TASKS.md` §1.1/§2.3 (single authoritative milestone sequence) instead of `IMPLEMENTATION_PLAN.md`; added Source of Truth note | Claude |
