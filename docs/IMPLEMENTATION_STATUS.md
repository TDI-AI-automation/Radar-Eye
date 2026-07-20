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
| Current phase | Implementation Phase 1 (per `PROJECT_CONTEXT.md`) — RM-01, RM-02, RM-DEV, RM-06, and RM-03 merged to `develop`; RM-04 implemented on `feature/shared-contracts`, pending review/merge |
| Repo stage | RM-01, RM-02, RM-DEV, RM-06, and RM-03 complete and merged into `develop` (commit `2cc8a2e`), following Principal Engineer review. RM-04 (Internal Event Bus) implemented on `feature/shared-contracts`: `shared/events/bus.py` — `EventBus` (abstract transport contract) and `InProcessEventBus` (initial implementation), per the RM-04 design review (see design note below). 9 new tests, 211 total passing repo-wide, 100% coverage; ruff/black/pre-commit clean; mypy advisory-only, 9 findings (accepted technical debt). Not yet merged into `develop` — pending Principal Engineer review. `feature/shared-contracts`, `feature/api`, `feature/developer-infrastructure`, and `feature/threat-engine` all retained as long-lived subsystem branches. All other `apps/*` and `services/*` packages remain stub `__init__.py` only — do not assume partial implementation exists anywhere else. |
| Design note (RM-04) | Per the RM-04 design review: delivery is best-effort/at-most-once per subscriber (no durable log); ordering is FIFO per producer per event type only (no cross-producer guarantee — sort by the envelope's `timestamp` if needed, per INV-014); back-pressure policy (explicit decision) — each subscriber has a bounded queue, `publish()` waits up to a configurable timeout (default 1s) for space, then drops for that subscriber only and emits a CRITICAL `SystemEvent` with subscriber identity/event type/queue depth/drop count; one subscriber's handler raising never affects other subscribers or the publisher; no replay capability (consumers reconstruct state from the database, per ADR-008). `EventBus` is an abstract contract with `InProcessEventBus` as the swappable initial implementation — same pattern as RM-03's `CredentialEncryptionProvider` — so a distributed transport can replace it later without touching producers/consumers. Explicitly out of scope: dynamic queue resizing, priority queues, dead-letter queues, replay, subscriber eviction. |
| Design note (RM-06) | Two design decisions from the RM-06 design review, approved before implementation: (1) rule precedence — FIRE overrides uniform-based rules (a fire hazard applies regardless of allegiance), so `military`/`unknown` + `fire` → HIGH, not ALLY/HUMAN_REVIEW; (2) `AlarmRequestedEvent`'s documented producer (Threat Engine, per EVENT_CONTRACTS.md) has no documented way to obtain the `incident_id` its payload requires, since `IncidentCreatedEvent` is produced by Incident Service (RM-07, not yet built) and Threat Engine isn't a documented consumer of it. RM-06 therefore emits an internal `EscalationSignal` (`INCIDENT_ELIGIBLE`/`ALARM_ELIGIBLE`, no `incident_id`) instead of constructing literal `IncidentCreatedEvent`/`AlarmRequestedEvent` instances. The real event assembly and Threat Engine ↔ Incident Service hand-off still needs to be designed once RM-04 (event bus) and RM-07 (Incident Service) exist — not an architecture change, but an open integration point to revisit then. |
| Design note (RM-03) | Per the RM-03 design review: persistence ownership is exclusive to `apps/api` (`docs/REPOSITORY_ARCHITECTURE.md`'s Ownership Rules) — no other subsystem defines ORM models, migrations, or holds a DB session; Threat Engine remains DB-independent, and future subsystems (Incident Service, etc.) will communicate through repositories and events, not direct DB access. Credential encryption uses the `CredentialEncryptionProvider` abstraction (not a direct Fernet dependency) so the concrete implementation is replaceable later. `users.role` and `camera_stream_profiles.transport` are plain `str` columns — no architecture document defines a value set for either yet; left unconstrained rather than inventing a taxonomy. |
| Primary branches | `develop` (integration branch, protected — no direct commits outside reviewed subsystem merges). `main` (production) does not exist yet — created only at the first full production release, per the Production Release Gate in `CLAUDE.md`. |
| Branching model | `main` ← `develop` ← long-lived subsystem branches ← optional short-lived ticket branches. `develop` is the active integration branch every subsystem milestone merges into after review; `main` receives merges from `develop` only at a validated production release. See Subsystem Status below for current branches, and `CLAUDE.md`'s "Git Branching & Merge Strategy" for the full model. |

---

## Next Immediate Action

**Current Milestone:**
RM-07 — Incident Service (see `docs/IMPLEMENTATION_ROADMAP.md`)

**Owning Branch:**
`feature/incident-service`

**Status:**
Not Started.

**Blocking Issues:**
None. RM-07 depends on RM-02, RM-03, RM-04, and RM-06 — all done (RM-04 implemented, pending review/merge into `develop`).

**Note:** RM-04 is implemented on `feature/shared-contracts` and passes all quality gates, but is pending Principal Engineer review/merge into `develop` — that review step is a separate action, not a blocker for starting RM-07.

---

## Milestone Status

Full milestone definitions, dependencies, and acceptance criteria live in `docs/IMPLEMENTATION_ROADMAP.md` — this table tracks completion status only and must not redefine what a milestone covers.

| Milestone | Status | Owning Branch |
|---|---|---|
| RM-01 | **Done** | `feature/api` |
| RM-02 | **Done** | `feature/shared-contracts` |
| RM-DEV | **Done** (merged into `develop`) | `feature/developer-infrastructure` |
| RM-06 | **Done** (merged into `develop`) | `feature/threat-engine` |
| RM-03 | **Done** (merged into `develop`) | `feature/api` |
| RM-04 | **Done** (implemented, pending review/merge into `develop`) | `feature/shared-contracts` |
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
| API service (FastAPI, persistence, auth/audit, lightweight health monitoring) | `apps/api/` | **In Progress** (RM-01, RM-03 done and merged) | `feature/api` | Shared contracts |
| Shared contracts (events, schemas, constants, internal event bus) | `shared/` | **In Progress** (RM-02 done and merged; RM-04 done, pending merge) | `feature/shared-contracts` | — |
| DeepStream pipeline (ingest → YOLO → NvDCF → ViT) | `apps/deepstream/` | Not Started | `feature/deepstream` | Shared contracts |
| Threat engine (rule-based scoring) | `services/threat_engine/` | **Done** (merged to `develop`) | `feature/threat-engine` | Shared contracts |
| Incident service (also owns the Alarm Service until it warrants its own subsystem — see RM-10) | `services/incident_service/` | Not Started | `feature/incident-service` | Threat engine, API service |
| Recording / evidence service | `services/recording/` | Not Started | `feature/recording` | Incident service |
| Camera calibration service | `services/calibration/` | Not Started | `feature/calibration` | Shared contracts |
| Frontend (Command Center UI) | external repo: `radar-eye-command` | Prototype UI complete, **not integrated** | `feature/frontend-integration` | API service |
| Deployment bundle / systemd | `deployments/`, `scripts/` | Not Started | `feature/deployment` | All backend subsystems |
| Developer infrastructure (formatting, linting, static analysis, dependency management, pre-commit, CI/CD, coverage tooling, developer workflow) | (repo-wide) | **Done** (merged to `develop`) | `feature/developer-infrastructure` | — |
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
| 2026-07-20 | RM-04 (Internal Event Bus) implemented on `feature/shared-contracts`, per an explicit design review approved before implementation began (delivery/ordering/back-pressure/replay policy, all summarized in Snapshot's Design Note). Delivers `shared/events/bus.py`: `EventBus` abstract contract, `InProcessEventBus` initial implementation. 9 new tests (delivery, multi-subscriber fan-out, event-type isolation, unsubscribe, per-producer ordering, fault-injection matching the roadmap's explicit acceptance criterion, back-pressure drop-and-alert, and the alert-under-load edge case), 211 total passing repo-wide, 100% coverage. Also corrected stale "event bus" wording in `PROJECT_CONTEXT.md` that had listed it under `apps/api` from before RM-04's branch ownership was settled. Not yet merged into `develop` — pending Principal Engineer review. |
| 2026-07-20 | RM-03 (Database Migrations & Persistence Layer) merged into `develop` (commit `2cc8a2e`) via a regular merge commit, following Principal Engineer review — approved with no blocking issues, including the required `CredentialEncryptionProvider` abstraction (Fernet as the initial implementation). Delivers ten SQLAlchemy models matching `DATABASE_SCHEMA.md` field-for-field, one thin repository per model, and one initial Alembic migration covering the full schema plus the `(camera_id, track_id)` active-incident dedup constraint. Verified against a live PostgreSQL container: reversibility across multiple up/down cycles, the dedup constraint, and every CHECK constraint. All gates re-verified clean on `develop` post-merge: 202 tests passing, 100% coverage. CI gained a `postgres:16-alpine` service container. `feature/api` retained as a long-lived subsystem branch. |
| 2026-07-20 | RM-06 (Threat Engine Service) merged into `develop` (commit `25c7f5b`) via a regular merge commit, following Principal Engineer review — approved with no blocking issues. Delivers `services/threat_engine`: `rules.py` (deterministic classify() covering every THREAT_ENGINE_SPEC.md table row), `engine.py` (per-track escalation/de-escalation state machine: 3-frame HIGH debounce, 1s/2s/3s incident/alarm timers, 10s/5s/3s de-escalation hysteresis, FIRE immediate bypass), `types.py` (`EscalationSignal` — see Snapshot's Design Note). 113 new tests (exhaustive rule table + precedence + determinism; engine timers/debounce/de-escalation/FIRE/HUMAN_REVIEW/track-isolation). All gates re-verified clean on `develop` post-merge: 176 tests passing, 100% coverage. `feature/threat-engine` retained as a long-lived subsystem branch. |
| 2026-07-20 | RM-DEV (Developer Infrastructure) merged into `develop` (commit `35e4f77`) via a regular merge commit, following Principal Engineer review — approved with no blocking issues. Delivers: ruff + black (required CI checks), mypy (advisory-only, `continue-on-error` in CI, 3 pre-existing findings recorded as technical debt for the owning subsystem to resolve when those files are next touched for functional work), pre-commit hooks (file hygiene + black + ruff; markdown docs excluded since they're under architecture-freeze change control), GitHub Actions CI scoped to PRs/pushes targeting `develop` only (not `feature/*`), pytest-cov coverage reporting with no minimum threshold enforced yet, and pinned dev-tool versions (ruff/black/mypy/pre-commit/pytest-cov/types-PyYAML) in `requirements-dev.txt`. Existing RM-01/RM-02 code brought to a clean black/ruff baseline (formatting-only). All gates re-verified clean on `develop` post-merge; 63 tests passing, 100% coverage on existing code. `feature/developer-infrastructure` retained as a long-lived subsystem branch. |
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

- 2026-07-20 — Alembic's `autogenerate` does not emit ENUM type drops in `downgrade()` for Postgres `sa.Enum` columns (it drops the tables but leaves the `CREATE TYPE`-created types behind), which breaks re-`upgrade()` after a `downgrade()` with "type already exists". Fixed by adding explicit `sa.Enum(name=...).drop(op.get_bind(), checkfirst=True)` calls to `downgrade()` for `incident_type`, `threat_level`, and `incident_status`. Watch for this on any future migration that adds a new Postgres-native enum column.
- 2026-07-20 — `Mapped[datetime | None]` / `Mapped[datetime]` columns without an explicit `DateTime(timezone=True)` default to `TIMESTAMP WITHOUT TIME ZONE` in Postgres, which raises at insert time against timezone-aware Python datetimes ("can't subtract offset-naive and offset-aware datetimes"). All `apps/api/app/models/*.py` timestamp columns now specify `DateTime(timezone=True)` explicitly; apply the same when adding new timestamp columns later.
- 2026-07-20 — `services/__init__.py` was missing since the original bootstrap (only its subdirectories had `__init__.py`); added it during RM-06 since it's needed to import `services.threat_engine` as an explicit package. Applies to the whole `services/` tree, not just threat_engine.
- 2026-07-20 — mypy's advisory findings now include 5 `isinstance(x, EventEnvelope[SomePayload])` notes ("Parameterized generics cannot be used with class or instance checks") from `tests/services/threat_engine/test_engine.py`. This is a static-analysis-only limitation — Pydantic's generic models make `isinstance` work correctly at runtime (all 176 tests pass) — not a real type error. Left as-is per RM-DEV's advisory-only mypy policy.
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
| 2026-07-20 | RM-04 (Internal Event Bus) implemented on `feature/shared-contracts` following an approved design review (delivery/ordering/back-pressure/replay policy decisions); corrected stale "event bus" ownership wording in `PROJECT_CONTEXT.md`; Snapshot, Next Immediate Action (now RM-07), Milestone Status, and Subsystem Status updated | Claude |
| 2026-07-20 | RM-03 (Database Migrations & Persistence Layer) merged into `develop` (`2cc8a2e`) following Principal Engineer review approval; all quality gates re-verified clean post-merge; Snapshot, Next Immediate Action, Milestone Status, and Subsystem Status updated to reflect the merge | Claude |
| 2026-07-20 | RM-06 (Threat Engine Service) merged into `develop` (`25c7f5b`) following Principal Engineer review approval; all quality gates re-verified clean post-merge; Snapshot, Next Immediate Action, Milestone Status, and Subsystem Status updated to reflect the merge | Claude |
| 2026-07-20 | RM-06 (Threat Engine Service) implemented on `feature/threat-engine` following an approved design review (fire-precedence and AlarmRequestedEvent/incident_id design decisions); Snapshot, Next Immediate Action (now RM-03), Milestone Status, and Subsystem Status updated | Claude |
| 2026-07-20 | RM-DEV (Developer Infrastructure) merged into `develop` (`35e4f77`) following Principal Engineer review approval; all quality gates re-verified clean post-merge; Snapshot, Next Immediate Action, Milestone Status, and Subsystem Status updated to reflect the merge | Claude |
| 2026-07-20 | RM-DEV implemented on `feature/developer-infrastructure` (ruff, black, mypy-advisory, pre-commit, CI, coverage reporting); Snapshot, Next Immediate Action (now RM-06), Milestone Status, and Subsystem Status updated | Claude |
| 2026-07-20 | Branch hierarchy restructured to main/develop model: `develop` established as the active integration branch (absorbed prior `master` history), RM-01 merged into `develop`, `feature/developer-infrastructure` created and given RM-DEV ownership (split from `feature/testing`); Snapshot, Next Immediate Action, Milestone Status, and Subsystem Status updated accordingly | Claude |
| 2026-07-19 | RM-02 merged into master (`8a39b34`); Next Immediate Action set to RM-DEV; Snapshot, Subsystem Status, and Recently Completed updated to reflect the merge and the pre-merge review fixes | Claude |
| 2026-07-19 | RM-02 complete: updated Snapshot, Next Immediate Action, Milestone Status, Subsystem Status, Recently Completed | Antigravity |
| 2026-07-18 | Initial version created | Claude |
| 2026-07-18 | Added Roadmap Progress, Next Immediate Action, and Architecture Contract sections; reordered recommended read sequence to place `TASKS.md` before this file | Claude |
| 2026-07-18 | Re-sourced Roadmap Progress from `TASKS.md` §1.1/§2.3 instead of `IMPLEMENTATION_PLAN.md`; added Source of Truth note | Claude |
| 2026-07-19 | Full reconciliation: removed the conflicting Roadmap Progress table (superseded by new `docs/IMPLEMENTATION_ROADMAP.md`); corrected Subsystem Status branches to the actual long-lived subsystem branches (`feature/api`, `feature/deepstream`, `feature/threat-engine`, `feature/incident-service`, `feature/recording`, `feature/calibration`, `feature/shared-contracts`, `feature/frontend-integration`, `feature/deployment`, `feature/testing`); removed the unratified `@agent-*` Owner column; corrected Next Immediate Action to RM-02; corrected Snapshot to reflect RM-01's completion; removed `develop` as a stated integration branch | Claude |
