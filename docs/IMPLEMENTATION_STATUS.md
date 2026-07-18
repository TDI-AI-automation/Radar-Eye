# Implementation Status

> **What this is:** A live rollup of *build state* — what exists in code today, on which subsystem branch, and what is blocking it. One row per subsystem, not per task.
>
> **What this is not:** Not architecture (see `ADR_INDEX.md` → `THREAT_ENGINE_SPEC.md` → `EVENT_CONTRACTS.md` → `DATABASE_SCHEMA.md` → `DEEPSTREAM_PIPELINE_SPEC.md` → `FRONTEND_BACKEND_CONTRACTS.md` → `AGENTS.md`, per `CLAUDE.md`'s priority order). Not the milestone sequence — that is `docs/IMPLEMENTATION_ROADMAP.md`, the single source of truth for what each `RM-XX` covers and in what order. Not a ticket backlog — that is `TASKS.md` (root), which owns individual tickets, acceptance criteria, and blockers (format currently under review). This file only tracks the subsystem-level *result* of that work: is the code there, and on which branch.
>
> **When to update:** Any time a subsystem's status, branch, or blocker changes — in the same PR/commit that causes the change, not on a schedule. Stale rows are worse than missing rows.
>
> **Who updates it:** Whoever changes the state — human or AI assistant.
>
> **Recommended read order when starting work in this repo:**
> `CLAUDE.md` → `PROJECT_CONTEXT.md` → `ADR_INDEX.md` → `TASKS.md` (root) → `docs/IMPLEMENTATION_ROADMAP.md` → **this file** → subsystem documentation / code.
> Read `docs/IMPLEMENTATION_ROADMAP.md` to know what a milestone means and its dependencies. Read this file to see how far the relevant subsystem branch has actually progressed, without re-deriving that from `git log` or the source tree. Then go to the architecture docs (priority order above) for how a subsystem must be built. Do not infer status from this file alone when the task is destructive or high-stakes — verify against the actual source tree first, since this file can lag reality.

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
| Current phase | Implementation Phase 1 (per `PROJECT_CONTEXT.md`) — RM-01 done, RM-02 next |
| Repo stage | RM-01 complete: `apps/api` foundation (settings, logging, DB engine/session factory, app factory) merged into `feature/api`. All other `apps/*` and `services/*` packages remain stub `__init__.py` only — do not assume partial implementation exists anywhere else. |
| Primary branch | `master` (protected — no direct commits per `PROJECT_CONTEXT.md`) |
| Branching model | Long-lived subsystem branches are the primary integration branches (see Subsystem Status below). `develop`'s role is not yet decided — do not treat it as an active integration branch. |

---

## Next Immediate Action

**Current Milestone:**
RM-02 — Shared Contracts Package (see `docs/IMPLEMENTATION_ROADMAP.md` for full deliverables/acceptance criteria)

**Owning Branch:**
`feature/shared-contracts`

**Status:**
Not Started — planning in progress.

**Blocking Issues:**
None. RM-02 depends only on RM-01, which is done.

---

## Milestone Status

Full milestone definitions, dependencies, and acceptance criteria live in `docs/IMPLEMENTATION_ROADMAP.md` — this table tracks completion status only and must not redefine what a milestone covers.

| Milestone | Status | Owning Branch |
|---|---|---|
| RM-01 | **Done** | `feature/api` |
| RM-02 | Not Started | `feature/shared-contracts` |
| RM-DEV | Not Started | `feature/testing` |
| RM-06 | Not Started | `feature/threat-engine` |
| RM-03 | Not Started | `feature/api` |
| RM-04 | Not Started | `feature/shared-contracts` |
| RM-07 | Not Started | `feature/incident-service` |
| RM-05 | Not Started | `feature/calibration` |
| RM-08 | Not Started | `feature/recording` |
| RM-09 | Not Started | `feature/api` |
| RM-10 | Not Started | `feature/incident-service` |
| RM-11 | Not Started | `feature/deepstream` |
| RM-12 | Not Started | `feature/api` |
| RM-13 | Not Started | `feature/frontend-integration` |
| RM-14 | Not Started | `feature/deployment` |
| RM-15 | Not Started | `feature/testing` |

---

## Subsystem Status

| Subsystem | Path | Status | Branch | Depends On |
|---|---|---|---|---|
| API service (FastAPI, persistence, event bus, auth/audit, lightweight health monitoring) | `apps/api/` | **In Progress** (RM-01 done) | `feature/api` | Shared contracts |
| Shared contracts (events, schemas, constants) | `shared/` | Not Started | `feature/shared-contracts` | — |
| DeepStream pipeline (ingest → YOLO → NvDCF → ViT) | `apps/deepstream/` | Not Started | `feature/deepstream` | Shared contracts |
| Threat engine (rule-based scoring) | `services/threat_engine/` | Not Started | `feature/threat-engine` | Shared contracts |
| Incident service (also owns the Alarm Service until it warrants its own subsystem — see RM-10) | `services/incident_service/` | Not Started | `feature/incident-service` | Threat engine, API service |
| Recording / evidence service | `services/recording/` | Not Started | `feature/recording` | Incident service |
| Camera calibration service | `services/calibration/` | Not Started | `feature/calibration` | Shared contracts |
| Frontend (Command Center UI) | external repo: `radar-eye-command` | Prototype UI complete, **not integrated** | `feature/frontend-integration` | API service |
| Deployment bundle / systemd | `deployments/`, `scripts/` | Not Started | `feature/deployment` | All backend subsystems |
| Developer tooling / validation & benchmarking | (repo-wide) | Not Started | `feature/testing` | — |

Status values: `Not Started` · `In Progress` · `Blocked` · `In Review` · `Done`.

No `Owner` column is maintained here — no ratified per-person/per-agent ownership roster currently exists in `AGENTS.md` or elsewhere. If one is adopted, add it back here rather than inventing handles.

---

## Blocked

Subsystem-level blockers only.

| Blocks | Reason |
|---|---|
| RM-11 (DeepStream AI Pipeline) sizing | Jetson compute budget for 20 cameras on one Jetson has never been measured on real hardware. Recommend an early partial-capacity spike before committing to the full integration timeline (see `docs/IMPLEMENTATION_ROADMAP.md`, RM-11 risk note). |
| RM-14 (Jetson Deployment) | DeepStream / JetPack / CUDA version combination actually flashed on target hardware has not been confirmed against NVIDIA's support matrix. |
| RM-08 (Recording & Evidence Service) | Not blocked, but carries a caveat: ADR-017's continuous 30-day retention policy has never been validated against actual available storage. RM-08 implements ADR-017 as documented, with retention duration as an isolated, configurable value specifically so this can be revisited without re-architecting the service if a future storage-sizing benchmark shows it infeasible. |

---

## Recently Completed

| Date | Item |
|---|---|
| 2026-07-19 | RM-01 (Repository & Runtime Foundation) implemented, tested (11 passing tests), merged into `feature/api` |
| 2026-07-19 | Repository governance reconciled with actual workflow: `docs/IMPLEMENTATION_ROADMAP.md` created as single source of truth for milestone sequencing; this document, `CLAUDE.md`, and `PROJECT_CONTEXT.md` updated to match the subsystem-branch model |
| 2026-07-16 | Repository skeleton, package structure for `apps/`, `services/`, `shared/` |
| 2026-07-16 | Architecture freeze v2 — priority-ordered spec set in place |
| — | Frontend prototype UI (separate repo, pre-dates this architecture — requires audit) |

---

## Implementation Notes

Running log of build-time findings that future contributors (human or AI) need but that don't belong in an ADR or spec. Newest first. Keep entries short. Move anything that becomes a durable architecture decision into an ADR instead of leaving it here.

- 2026-07-19 — This document previously carried its own "Roadmap Progress" table (RM-01–RM-07) sourced from `docs/TASKS.md`'s `RE-xxx` ranges. That table used the same `RM-XX` IDs as the actual, approved roadmap to mean entirely different milestones (e.g. its RM-01 was "AI model optimization," not "Repository & Runtime Foundation," which is what was actually built). It has been replaced by a reference to `docs/IMPLEMENTATION_ROADMAP.md`. Do not recreate a second milestone definition in this file.
- 2026-07-19 — `feature/backend-foundation` and the original `feature/rm-01-repository-runtime-foundation` branch have been retired; RM-01's work now lives on `feature/api`.
- 2026-07-19 — Except for `apps/api/`, every `apps/*` and `services/*` package still contains only `__init__.py`. Treat any subsystem not listed as "In Progress" or later above as literally empty before starting work.

---

## Related Documents

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative milestone sequence, deliverables, acceptance criteria, dependencies
- `TASKS.md` (root) — ticket-level backlog; format under review, unchanged for now
- `ADR_INDEX.md` — accepted architecture decisions
- `PROJECT_CONTEXT.md` — static project facts (hardware, repos, stack) and the subsystem-branch model
- `CLAUDE.md` — repository operating manual, including "Git Branching & Merge Strategy"
- `AGENTS.md` — runtime pipeline agent roster and communication rules

Note: `docs/TASKS.md` (a different file from root `TASKS.md`) is a candidate for archival per an earlier documentation-consolidation review and is no longer treated as authoritative for milestone sequencing or subsystem branch assignment. That review has not yet been executed as a file change.

---

## Changelog

| Date | Change | By |
|---|---|---|
| 2026-07-18 | Initial version created | Claude |
| 2026-07-18 | Added Roadmap Progress, Next Immediate Action, and Architecture Contract sections; reordered recommended read sequence to place `TASKS.md` before this file | Claude |
| 2026-07-18 | Re-sourced Roadmap Progress from `TASKS.md` §1.1/§2.3 instead of `IMPLEMENTATION_PLAN.md`; added Source of Truth note | Claude |
| 2026-07-19 | Full reconciliation: removed the conflicting Roadmap Progress table (superseded by new `docs/IMPLEMENTATION_ROADMAP.md`); corrected Subsystem Status branches to the actual long-lived subsystem branches (`feature/api`, `feature/deepstream`, `feature/threat-engine`, `feature/incident-service`, `feature/recording`, `feature/calibration`, `feature/shared-contracts`, `feature/frontend-integration`, `feature/deployment`, `feature/testing`); removed the unratified `@agent-*` Owner column; corrected Next Immediate Action to RM-02; corrected Snapshot to reflect RM-01's completion; removed `develop` as a stated integration branch | Claude |
