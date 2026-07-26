# RM-12 — API Service (REST + WebSocket): Implementation Plan

**Status:** Implemented. All 6 phases below are complete on
`feature/RM-12-api-service`, reviewed in the RM-12 Release Review, and
approved. This document now records what was actually built, not a plan
awaiting execution. Of the architecture doc's two items deferred to this
plan: password hashing was decided as **bcrypt** (`apps/api/app/security/
auth.py` — no native `argon2` build dependency needed for a Jetson-class
target, simpler dependency footprint; an implementation-detail choice, not
an architectural one); the role taxonomy remains the client-owned open
question it always was (`docs/OPEN_QUESTIONS.md` Q-009) — Phase 1 built
against the proposed `admin`/`operator`/`viewer` taxonomy without claiming
to ratify it. Two capabilities originally scoped into Phase 4/5 were
deferred during implementation rather than built speculatively — see
those phases' notes below and `docs/OPEN_QUESTIONS.md` Q-014/Q-015.
Updated per the Architecture Readiness Review's three findings (incident
lifecycle ownership, missing error envelope, `/ws/camera-health`'s missing
schemas) — see architecture §3.3/§3.6/§3.5 for the decisions this plan
reflects.

Per the project's own established principle (`docs/IMPLEMENTATION_STATUS.md`,
Design note (RM-11): *"infrastructure first, integration second,
optimization last"*), this plan sequences RM-12 the same way: auth/audit
foundation first (everything else depends on it for role-gating), then
read-only REST surfaces (lowest risk, no mutation/audit concerns), then
mutating REST surfaces (need auth + audit both working), then the
WebSocket bridge last (depends on nothing this plan builds except the event
bus, which already exists — sequenced last because it's the newest
category of code in this repo, no existing pattern to lean on).

---

## Phase 1 — Auth foundation

**Files:**
- `apps/api/app/security/auth.py` — password hashing (verify/hash), JWT
  encode/decode, the local-user auth provider behind a small interface
  (per architecture §3.2's "LDAP-swappable" requirement).
- `apps/api/app/security/dependencies.py` — FastAPI `Depends()` helpers:
  `get_current_user`, `require_role(minimum_role)`.
- `apps/api/app/config.py` — add JWT signing secret + token TTL fields to
  `EnvSettings` (environment-only, matching existing `encryption_key`
  handling — no new pattern).
- `apps/api/app/models/user.py` — confirm/tighten the `role` column
  (currently free-text `str`) to the approved taxonomy from architecture
  §3.2, once confirmed. If a DB-level constraint is added, a new Alembic
  migration.
- New router: `apps/api/app/routers/auth.py` — login (issue tokens),
  refresh.
- `shared/schemas/api.py` — add `ApiError(code: str, message: str)` and
  extend `ApiResponse[T]` with `error: ApiError | None = None` (additive,
  backward-compatible — architecture §3.6). Cross-subsystem touch
  (`feature/shared-contracts`), same consideration as the Phase 4 note
  below.
- `apps/api/app/main.py` — one global exception handler translating
  `HTTPException`/validation errors into the `ApiResponse(success=False,
  error=...)` shape, registered in `create_app()`. Established here, in
  Phase 1, because auth's 401/403 responses are the first real consumer —
  every later phase's error responses reuse this, none invents its own.

**Tests:** password hashing round-trip; token encode/decode + expiry;
`require_role` dependency (allowed/denied cases) using an authenticated
test client fixture (new — see Phase 5); the global exception handler
produces the documented error shape for a 401, a 404, and a validation
error, exercised via one throwaway test route each.

**Gate before Phase 2:** full quality gates green; auth dependency
demonstrably rejects an unauthenticated/under-privileged request against a
throwaway test route.

---

## Phase 2 — Audit foundation

**Files:**
- New Alembic migration: `audit_log` table (architecture §3.4's fields).
- `apps/api/app/models/audit_log.py`, `apps/api/app/repositories/audit_log.py`
  (same generic-repository pattern as every other repository in
  `apps/api/app/repositories/`).
- `apps/api/app/audit/logger.py` — `AuditLogger`, constructed in `main.py`'s
  `create_app()`, stashed on `app.state` (mirrors `HealthCollector` exactly).

**Tests:** repository CRUD; `AuditLogger.record()` writes the expected row.

**Gate before Phase 3:** full quality gates green.

---

## Phase 3 — Read-only REST endpoints

Lowest-risk category — no auth-role complexity beyond "any authenticated
user," no audit writes (architecture §3.4 — reads aren't audited), thin
wrappers over already-existing repositories.

**New router modules** (each returns `ApiResponse[T]`, uses existing
repositories, existing or newly-added schemas per architecture §2/§3.1):

| Router | Routes | Schema work needed |
|---|---|---|
| `cameras.py` | `GET /cameras`, `GET /cameras/{id}`, `GET /cameras/{id}/calibration` | `CameraSchema` exists; calibration response schema is new (thin wrap of `CameraCalibrationRepository`). `GET /cameras/{id}/health` is **not** listed here — it already exists, shipped in RM-09's `health.py`, no new work. |
| `threats.py` | `GET /threats/active` | `ActiveThreatSchema` exists — but there's no persistence table for "active threats" (Threat Engine doesn't persist assessments, only publishes events). This endpoint's actual data source needs one more design check before Phase 3 starts: either a new in-memory "recent threats" cache fed by the event bus (mirrors `HealthCollector`'s in-memory pattern) or a decision that this endpoint is WS-only in practice. Flagged here, not resolved — first task of this phase. |
| `incidents.py` (read routes) | `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/events`, `GET /incidents/{id}/evidence`, `GET /incidents/open` | `IncidentSchema`/`IncidentSummarySchema` exist; `/evidence` sub-resource needs a small new schema (recording/snapshot summary) |
| `reviews.py` (read routes) | `GET /reviews`, `GET /reviews/{id}` | `HumanReviewSchema` exists |
| `calibration.py` (read routes) | `GET /calibration/cameras`, `GET /calibration/results`, `GET /calibration/{camera_id}` | New schemas (thin wraps of `CameraCalibrationRepository`) |
| `evidence.py` | `GET /evidence`, `GET /evidence/{id}`, `GET /recordings`, `GET /recordings/{id}`, `GET /recordings/{id}/download`, `GET /snapshots/{id}`, `GET /snapshots/{id}/download` | New schemas over `RecordingRepository`/`SnapshotRepository`. `/download` routes need a streaming-file-response design decision (direct file stream vs. signed URL) — not yet made, first task touching these two routes. |
| `analytics.py` | `GET /analytics/threats`, `GET /analytics/incidents`, `GET /analytics/cameras`, `GET /analytics/system` | New schemas; per architecture §4, straightforward repository-query aggregation only — no new analytics infrastructure |

**Tests:** contract tests per route (status code, `ApiResponse` envelope
shape, schema field match against `FRONTEND_BACKEND_CONTRACTS.md`) — see
Phase 5 for the shared harness these all use.

**Gate before Phase 4:** full quality gates green; every read-only route in
`FRONTEND_BACKEND_CONTRACTS.md` implemented and contract-tested.

---

## Phase 4 — Mutating REST endpoints

Needs Phase 1 (auth/roles) and Phase 2 (audit) both working — every route
here is `PATCH`/`POST` and role-gated per architecture §3.2, audit-logged
per §3.4.

**New/extended router modules:**

| Router | Routes | Role gate (proposed, per architecture §3.2's taxonomy) |
|---|---|---|
| `incidents.py` (write route) | `PATCH /incidents/{id}` | `operator`. **First task in this row, before the route itself:** add a new public method to `IncidentService` for operator-initiated transitions (architecture §3.3 — found during Architecture Readiness Review). The route calls this method in-process (same pattern `ThreatEngineRuntimeAdapter` already uses to call `IncidentService`), never writes to the `incidents` table directly via `IncidentRepository`. This touches `services/incident_service` (owned by `feature/incident-service`) — flag/coordinate per `CLAUDE.md`'s Multi-Agent Collaboration rule even if implemented in this same PR. |
| `reviews.py` (write routes) | `PATCH /reviews/{id}`, `POST /reviews/{id}/confirm-military`, `POST /reviews/{id}/confirm-civilian`, `POST /reviews/{id}/escalate`, `POST /reviews/{id}/dismiss` | `operator` — matches `CLAUDE.md`'s Human Review Rules (unknown uniforms must never auto-resolve; these are exactly the four allowed operator actions) |
| `cameras.py` (write route) | `PATCH /cameras/{id}` | `admin` |
| `calibration.py` (write routes) | `POST /calibration/start`, `POST /calibration/validate` | `operator` |
| `users.py` | `GET /users`, `PATCH /users/{user_id}` | `admin` |

**`config.py` — Deferred, not implemented (`docs/OPEN_QUESTIONS.md` Q-014).**
`GET`/`PATCH /config` were removed from this phase's scope during
implementation: no configuration persistence model exists anywhere in
`docs/DATABASE_SCHEMA.md`/`docs/DOMAIN_MODEL.md` (unlike `audit_log`,
there was no conceptual entity to anchor a schema on), so building it
would mean inventing new architecture rather than implementing approved
architecture. Requires its own Configuration Management milestone.

Note: `users.py` is the only router where the `GET` route is built here in
Phase 4 rather than Phase 3, despite being a read — unlike Phase 3's
routes (open to any authenticated user), the user list is `admin`-only to
*read*, not just to write, so it carries the same role-gating work as this
phase's other routes and gains nothing from being split across two
phases. `PATCH /users` was corrected to `PATCH /users/{user_id}` during
implementation — the contract document's original path had no identifier,
unlike every other mutating route in it (see
`docs/FRONTEND_BACKEND_CONTRACTS.md`'s Settings section notes).

**Tests:** contract tests (as Phase 3) plus role-gate tests (correct role
succeeds, wrong role gets 403, unauthenticated gets 401) plus an audit-log
assertion (the action produced the expected `audit_log` row) for every
mutating route.

**Gate before Phase 5:** full quality gates green; every route in
`FRONTEND_BACKEND_CONTRACTS.md` now implemented except the deferred
`GET`/`PATCH /config` (`docs/OPEN_QUESTIONS.md` Q-014); role-gating and
audit logging demonstrated on every mutating route, not just spot-checked.

---

## Phase 5 — WebSocket bridge

**Files:**
- `apps/api/app/websockets/connection_manager.py` — per-channel connection
  tracking (accept, register, broadcast, remove-on-disconnect).
- `apps/api/app/websockets/bridge.py` — the `EventBus.subscribe()` →
  translate → broadcast adapter (architecture §3.5), one per channel:
  `threats`, `incidents`, `camera_health`, `reviews`, `alarms`. `tracking`
  is **deferred, not implemented** (`docs/OPEN_QUESTIONS.md` Q-015) — the
  clarifying question this row originally flagged (what does `/ws/tracking`
  carry, if not one of the 10 existing event types?) was asked and
  answered: defer it. No event model, payload, or publisher exists for
  live tracking data anywhere in the codebase; building one would require
  its own design pass (event schema, publish frequency, publisher
  ownership, and how it interacts with `docs/DATABASE_SCHEMA.md`'s
  Explicit Non-Persistence Rules), not a smallest-reasonable-choice
  resolution like this phase's other decisions.
- `shared/schemas/camera.py` — two new schemas needed for `camera_health`
  specifically, found during Architecture Readiness Review (architecture
  §3.5's correction): `CameraDisconnectedSchema` (from
  `CameraDisconnectedPayload`) and `SystemEventSchema` (from
  `SystemEventPayload`) — this channel forwards both event types per
  `FRONTEND_BACKEND_CONTRACTS.md`, neither of which has a frontend schema
  today (unlike every other channel, which reuses an already-built one).
- New router/endpoint registrations in `main.py`: `/ws/threats`,
  `/ws/incidents`, `/ws/camera-health`, `/ws/reviews`, `/ws/alarms`
  (`/ws/tracking` deferred — see above).
- Bridge lifecycle wired into `main.py`'s `lifespan` (subscribe on startup,
  unsubscribe on shutdown, matching the engine-dispose pattern already
  there).

**Tests:** connect a test WebSocket client, publish a real event on a
real (test) `InProcessEventBus`, assert the translated frontend-schema
message arrives — this is the new test harness the architecture doc's
Risks section flags as greenfield. The **end-to-end latency test**
(explicit acceptance criterion) measures wall-clock time from
`bus.publish()` to the message arriving at the WebSocket client, asserting
it's comfortably under the 2s acceptance bound (architecture §3.5 argues
this should be sub-millisecond in practice; the test proves it, doesn't
assume it).

**Gate before Phase 6:** full quality gates green; every WS channel in
`FRONTEND_BACKEND_CONTRACTS.md` implemented and latency-tested except the
deferred `/ws/tracking` (`docs/OPEN_QUESTIONS.md` Q-015).

---

## Phase 6 — Full contract verification + final quality gates

- One consolidated contract-test pass asserting every single endpoint/
  channel in `FRONTEND_BACKEND_CONTRACTS.md` exists and matches (systematic
  cross-check, not just "the tests I happened to write per phase") —
  mirrors this repo's existing convention of a final verification pass
  before calling a milestone done (see `docs/RM-11_SIV_ENGINEERING_REVIEW.md`
  for the precedent this follows).
- Full repository quality gates (`ruff`, `black`, `mypy`, `pytest --cov`).
- Update `docs/IMPLEMENTATION_STATUS.md` (Milestone Status, Subsystem
  Status, Recently Completed, Changelog) per `CLAUDE.md`'s Completion
  Procedure.

---

## Cross-cutting notes

- **No opportunistic refactoring.** `health.py`/`HealthCollector` are the
  established pattern to *follow*, not to refactor while touching adjacent
  code — per `CLAUDE.md`'s Implementation Rules.
- **Each phase is quality-gated independently**, mirroring the discipline
  already established and explicitly praised in this repo's RM-11.SIV work
  (`docs/RM-11_SIV_ENGINEERING_REVIEW.md`'s own review of that phased
  approach) — not a new process being introduced for RM-12.
- **Every phase's failure paths get verified before its happy paths**,
  same established convention (RM-11.SIV's approved implementation order
  explicitly required this) — e.g. Phase 1's "unauthenticated request
  rejected" test before "authenticated request succeeds," Phase 4's 401/403
  cases before the 200 case.
- **Items flagged as "not yet resolved" during planning** (the
  `/threats/active` data source, `/download` route design, `/ws/tracking`'s
  payload shape) were each resolved during their own phase, not guessed at
  during planning: `/threats/active` reads from a new in-memory
  `ActiveThreatCache` (Phase 3); `/download` streams files directly via
  `FileResponse`, no signed-URL infrastructure (Phase 3); `/ws/tracking`
  was deferred entirely rather than built speculatively (Phase 5,
  `docs/OPEN_QUESTIONS.md` Q-015).
