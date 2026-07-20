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
| Current phase | Implementation Phase 1 (per `PROJECT_CONTEXT.md`) — RM-01 and RM-02 merged to `develop`; RM-DEV implemented on `feature/developer-infrastructure`, pending review/merge; RM-06 next |
| Repo stage | RM-01 and RM-02 complete and merged into `develop` (63 tests passing). RM-DEV (Developer Infrastructure) implemented on `feature/developer-infrastructure`: `pyproject.toml` (ruff/black/mypy/coverage config), `.pre-commit-config.yaml`, GitHub Actions CI (`.github/workflows/ci.yml`, triggers on PRs/pushes to `develop` only), `ruff`/`black`/`mypy`/`pre-commit`/`pytest-cov` added to `requirements-dev.txt`. Existing RM-01/RM-02 code reformatted to a clean black/ruff baseline (formatting-only, no behavior change); mypy runs advisory-only (does not fail CI) and currently reports 3 pre-existing findings, left unresolved as out of RM-DEV's scope. All quality gates (black, ruff, pytest, pre-commit) pass clean; not yet merged into `develop`. `feature/shared-contracts`, `feature/api`, and `feature/developer-infrastructure` all retained as long-lived subsystem branches. All other `apps/*` and `services/*` packages remain stub `__init__.py` only — do not assume partial implementation exists anywhere else. |
| Primary branches | `develop` (integration branch, protected — no direct commits outside reviewed subsystem merges). `main` (production) does not exist yet — created only at the first full production release, per the Production Release Gate in `CLAUDE.md`. |
| Branching model | `main` ← `develop` ← long-lived subsystem branches ← optional short-lived ticket branches. `develop` is the active integration branch every subsystem milestone merges into after review; `main` receives merges from `develop` only at a validated production release. See Subsystem Status below for current branches, and `CLAUDE.md`'s "Git Branching & Merge Strategy" for the full model. |

---

## Next Immediate Action

**Current Milestone:**
RM-06 — Threat Engine Service (see `docs/IMPLEMENTATION_ROADMAP.md`)

**Owning Branch:**
`feature/threat-engine`

**Status:**
Not Started.

**Blocking Issues:**
None. RM-06 depends only on RM-02, which is done and merged into `develop`.

**Note:** RM-DEV is implemented on `feature/developer-infrastructure` and passes all quality gates, but has not yet been through review/merge into `develop` — that is a separate, reviewed integration step, not a blocker for starting RM-06. RM-03 (Database), RM-04 (Event Bus), and other RM-02-only-dependent milestones also remain available in parallel per the roadmap's parallelization guidance.

---

## Milestone Status

Full milestone definitions, dependencies, and acceptance criteria live in `docs/IMPLEMENTATION_ROADMAP.md` — this table tracks completion status only and must not redefine what a milestone covers.

| Milestone | Status | Owning Branch |
|---|---|---|
| RM-01 | **Done** | `feature/api` |
| RM-02 | **Done** | `feature/shared-contracts` |
| RM-DEV | **Done** (implemented, pending merge into `develop`) | `feature/developer-infrastructure` |
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
| API service (FastAPI, persistence, event bus, auth/audit, lightweight health monitoring) | `apps/api/` | **In Progress** (RM-01 done, merged to `develop`) | `feature/api` | Shared contracts |
| Shared contracts (events, schemas, constants) | `shared/` | **Done** (merged to `develop`) | `feature/shared-contracts` | — |
| DeepStream pipeline (ingest → YOLO → NvDCF → ViT) | `apps/deepstream/` | Not Started | `feature/deepstream` | Shared contracts |
| Threat engine (rule-based scoring) | `services/threat_engine/` | Not Started | `feature/threat-engine` | Shared contracts |
| Incident service (also owns the Alarm Service until it warrants its own subsystem — see RM-10) | `services/incident_service/` | Not Started | `feature/incident-service` | Threat engine, API service |
| Recording / evidence service | `services/recording/` | Not Started | `feature/recording` | Incident service |
| Camera calibration service | `services/calibration/` | Not Started | `feature/calibration` | Shared contracts |
| Frontend (Command Center UI) | external repo: `radar-eye-command` | Prototype UI complete, **not integrated** | `feature/frontend-integration` | API service |
| Deployment bundle / systemd | `deployments/`, `scripts/` | Not Started | `feature/deployment` | All backend subsystems |
| Developer infrastructure (formatting, linting, static analysis, dependency management, pre-commit, CI/CD, coverage tooling, developer workflow) | (repo-wide) | **Done** (implemented on branch, pending merge into `develop`) | `feature/developer-infrastructure` | — |
| Testing (validation, regression testing, benchmarking, soak testing, evaluation) | (repo-wide) | Not Started | `feature/testing` | — |

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
| 2026-07-20 | RM-DEV (Developer Infrastructure) implemented on `feature/developer-infrastructure`: ruff + black (required CI checks), mypy (advisory-only, `continue-on-error` in CI, 3 pre-existing findings reported and left unresolved as out of scope), pre-commit hooks (file hygiene + black + ruff; markdown docs excluded since they're under architecture-freeze change control), GitHub Actions CI scoped to PRs/pushes targeting `develop` only (not `feature/*`), pytest-cov coverage reporting with no minimum threshold enforced yet. Existing RM-01/RM-02 code brought to a clean black/ruff baseline (formatting-only). All gates pass; 63 tests still passing. Not yet merged into `develop` — pending review. |
| 2026-07-20 | Branch hierarchy restructured to `main` (production) / `develop` (integration) per updated governance: `develop` fast-forwarded to absorb the prior `master` history, `feature/api` (RM-01) merged into `develop` (commit `cbcc49c`), 63 tests passing. `main` intentionally not created yet — reserved for the first full production release. `feature/developer-infrastructure` created as a new long-lived subsystem branch (formatting, linting, static analysis, dependency management, pre-commit, CI/CD, coverage tooling, developer workflow), split out from `feature/testing`, which now scopes exclusively to validation/regression/benchmarking/soak testing/evaluation. RM-DEV ownership moved to `feature/developer-infrastructure`. |
| 2026-07-19 | RM-02 (Shared Contracts Package) merged into `master` (commit `8a39b34`) via a regular merge commit, following Principal Engineer review. Two blocking issues were found and fixed pre-merge: `IncidentStatus` used `CLOSED` and omitted `ARCHIVED` (corrected to match `docs/INCIDENT_LIFECYCLE.md`'s five-state lifecycle: NEW/ACTIVE/ACKNOWLEDGED/RESOLVED/ARCHIVED); `ReviewStatus` used `PENDING` instead of `OPEN` (corrected to match `docs/DATABASE_SCHEMA.md`'s `human_review_items.status` values). `feature/shared-contracts` retained as a long-lived subsystem branch. |
| 2026-07-19 | RM-02 (Shared Contracts Package) implemented and tested on `feature/shared-contracts`: `shared/constants` (ThreatLevel, DistanceZone, WeaponType, UniformClass, IncidentType, IncidentStatus), `shared/events` (EventEnvelope + 10 typed event aliases matching EVENT_CONTRACTS.md), `shared/schemas` (ApiResponse + threat/incident/review/camera/alarm schemas from FRONTEND_BACKEND_CONTRACTS.md). `conftest.py` and `pytest.ini` added at repo root. 52 tests passing. |
| 2026-07-19 | RM-01 (Repository & Runtime Foundation) implemented, tested (11 passing tests), merged into `feature/api` |
| 2026-07-19 | Repository governance reconciled with actual workflow: `docs/IMPLEMENTATION_ROADMAP.md` created as single source of truth for milestone sequencing; this document, `CLAUDE.md`, and `PROJECT_CONTEXT.md` updated to match the subsystem-branch model |
| 2026-07-16 | Repository skeleton, package structure for `apps/`, `services/`, `shared/` |
| 2026-07-16 | Architecture freeze v2 — priority-ordered spec set in place |
| — | Frontend prototype UI (separate repo, pre-dates this architecture — requires audit) |

---

## Implementation Notes

Running log of build-time findings that future contributors (human or AI) need but that don't belong in an ADR or spec. Newest first. Keep entries short. Move anything that becomes a durable architecture decision into an ADR instead of leaving it here.

- 2026-07-20 — `requirements-dev.txt`'s dev/quality tools (ruff, black, mypy, pre-commit, types-PyYAML) are pinned to exact versions rather than `>=`, so CI, pre-commit, and local dev installs can't drift apart. `ruff`/`black` pins match the versions pinned in `.pre-commit-config.yaml` exactly. Runtime deps in `requirements.txt` and the RM-01-era `pytest`/`pytest-asyncio`/`httpx` entries remain `>=` — unchanged, out of scope for this update.
- 2026-07-20 — Pre-commit's generic file-hygiene hooks (trailing-whitespace, end-of-file-fixer) initially reformatted every architecture/governance markdown file repo-wide on first run. That was reverted, and `.pre-commit-config.yaml` now excludes all `*.md` files repo-wide (`exclude: '\.md$'`) — those docs are under architecture-freeze change control and must never be touched by generic formatting tooling.
- 2026-07-20 — `master` is superseded by `develop` as the active integration branch (`main` reserved for production releases; not created yet). Any doc, script, or CI config still referencing `master` as the branch to build against should be treated as stale and pointed at `develop` instead.
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
| 2026-07-20 | RM-DEV implemented on `feature/developer-infrastructure` (ruff, black, mypy-advisory, pre-commit, CI, coverage reporting); Snapshot, Next Immediate Action (now RM-06), Milestone Status, and Subsystem Status updated | Claude |
| 2026-07-20 | Branch hierarchy restructured to main/develop model: `develop` established as the active integration branch (absorbed prior `master` history), RM-01 merged into `develop`, `feature/developer-infrastructure` created and given RM-DEV ownership (split from `feature/testing`); Snapshot, Next Immediate Action, Milestone Status, and Subsystem Status updated accordingly | Claude |
| 2026-07-19 | RM-02 merged into master (`8a39b34`); Next Immediate Action set to RM-DEV; Snapshot, Subsystem Status, and Recently Completed updated to reflect the merge and the pre-merge review fixes | Claude |
| 2026-07-19 | RM-02 complete: updated Snapshot, Next Immediate Action, Milestone Status, Subsystem Status, Recently Completed | Antigravity |
| 2026-07-18 | Initial version created | Claude |
| 2026-07-18 | Added Roadmap Progress, Next Immediate Action, and Architecture Contract sections; reordered recommended read sequence to place `TASKS.md` before this file | Claude |
| 2026-07-18 | Re-sourced Roadmap Progress from `TASKS.md` §1.1/§2.3 instead of `IMPLEMENTATION_PLAN.md`; added Source of Truth note | Claude |
| 2026-07-19 | Full reconciliation: removed the conflicting Roadmap Progress table (superseded by new `docs/IMPLEMENTATION_ROADMAP.md`); corrected Subsystem Status branches to the actual long-lived subsystem branches (`feature/api`, `feature/deepstream`, `feature/threat-engine`, `feature/incident-service`, `feature/recording`, `feature/calibration`, `feature/shared-contracts`, `feature/frontend-integration`, `feature/deployment`, `feature/testing`); removed the unratified `@agent-*` Owner column; corrected Next Immediate Action to RM-02; corrected Snapshot to reflect RM-01's completion; removed `develop` as a stated integration branch | Claude |
