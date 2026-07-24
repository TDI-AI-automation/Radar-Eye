# RM-12 — API Service (REST + WebSocket): Architecture

**Status:** Draft — planning only, per `docs/IMPLEMENTATION_ROADMAP.md`'s RM-12
entry and the Principal Engineer's explicit instruction. No implementation
code has been written against this document. Requires review and approval,
alongside `docs/RM-12_IMPLEMENTATION_PLAN.md`, before implementation begins.

**Owning branch:** `feature/RM-12-api-service` (cut from `feature/api`,
fast-forwarded to `develop`'s tip — see that branch's history for the exact
base commit).

---

## 1. Scope, per `docs/IMPLEMENTATION_ROADMAP.md`

**Deliverables:** every endpoint/channel in `docs/FRONTEND_BACKEND_CONTRACTS.md`;
auth + audit (both inside `apps/api`); bridges the event bus to WebSocket.

**Acceptance:** contract-tested against `FRONTEND_BACKEND_CONTRACTS.md`;
alert latency ≤2s; role-gated routes enforced.

**Testing:** contract tests; WebSocket end-to-end latency test.

---

## 2. Current State (verified against source, not assumed)

- **Routers:** exactly one exists — `apps/api/app/routers/health.py` (6
  routes, all from RM-09). No other router module exists. `apps/api/app/main.py`
  registers only `health_router`; no middleware (no CORS, no auth, no
  request-ID/audit) is registered anywhere.
- **Persistence:** RM-03 already delivered models + repositories for
  `cameras`, `camera_stream_profiles`, `camera_calibrations`, `incidents`,
  `incident_events`, `human_review_items`, `snapshots`, `recordings`,
  `system_events`, `users`. RM-12's REST layer is mostly a thin surface over
  data that already persists — not new persistence design, except where
  noted in §4 (audit).
- **Schemas:** `shared/schemas/` already has response/WS-body schemas for
  health, incidents, threats, reviews, cameras, and alarms — several
  (`IncidentCreatedSchema`, `IncidentUpdatedSchema`, `ThreatAssessmentSchema`,
  `HumanReviewSchema`, `CameraHealthSchema`, `AlarmSchema`) were built
  specifically to double as WebSocket message bodies matching
  `FRONTEND_BACKEND_CONTRACTS.md`'s "Frontend Event Models" shapes. No
  schemas exist yet for users/roles/permissions, evidence/recordings/
  snapshots, calibration, config/settings, analytics, or camera-tracking.
- **Event bus:** `shared/events/bus.py`'s `InProcessEventBus` (RM-04) already
  publishes every event type `FRONTEND_BACKEND_CONTRACTS.md`'s WebSocket
  section needs: `ThreatAssessmentEvent`, `IncidentCreatedEvent`,
  `IncidentUpdatedEvent`, `HumanReviewItemCreatedEvent`,
  `AlarmRequestedEvent`, `CameraDisconnectedEvent`, `SystemEvent`. RM-12's WS
  work is subscribing and translating, not producing new event types.
- **Auth/audit/roles:** none of this exists in code. `users.role` is an
  unconstrained `str` column — its own model docstring states RM-12 is
  expected to define and enforce an actual taxonomy. No audit-log table
  exists (`system_events` and `incident_events` are operational logs, not
  user-action audit trails). No JWT/session/password-hashing code exists
  anywhere in the repo.
- **Structural precedent for where auth/audit should live:**
  `PROJECT_CONTEXT.md`'s subsystem table states `apps/api` owns
  "persistence, auth/audit, lightweight health monitoring" as one service —
  not separate microservices. RM-09's `HealthCollector` (constructed in
  `main.py`'s `create_app()`, stashed on `app.state`, injected into routers
  via `Depends()`) is the established structural pattern to reuse for an
  analogous `AuditLogger`/auth dependency, not a new pattern to invent.

---

## 3. Architecture Decisions

### 3.1 Router organization

One router module per `FRONTEND_BACKEND_CONTRACTS.md` section, mirroring
`health.py`'s existing shape (a single `APIRouter()`, route functions
returning `ApiResponse[T]`, DB session and any collaborator pulled from
`request.app.state` via a `Depends()` helper):

`cameras.py`, `threats.py`, `incidents.py`, `analytics.py`, `config.py`,
`users.py`, `reviews.py`, `calibration.py`, `evidence.py` (covers
`/recordings*`, `/snapshots*`, `/evidence*` — all three are evidence-domain
reads over the existing `RecordingRepository`/`SnapshotRepository`).

No `/api/v1` prefix — `FRONTEND_BACKEND_CONTRACTS.md`'s Base Path is
`/api/v1` in name, but RM-09's own corrected precedent (a Repository
Integration Audit finding) established that this repo's actual routes carry
no version prefix, matching what RM-09 shipped and what the frontend
contract's own endpoint table implies by omission everywhere except the
"API Standards" header. This PR does not resolve that documented open
question (`docs/OPEN_QUESTIONS.md` territory) — it follows RM-09's existing,
already-corrected precedent for consistency, and flags introducing a real
version prefix as out of scope, same as RM-09 left it.

No GraphQL — `CLAUDE.md`'s Backend Constraints are explicit on this.

### 3.2 Authentication

**Decision proposed for approval:** JWT-based, stateless, local users only
(ADR-009's Initial State), structured behind a thin provider interface so
LDAP/AD (ADR-009's Future State) can be added later without reworking every
route's auth dependency.

- Passwords: hashed with a modern adaptive hash (argon2 or bcrypt — final
  choice deferred to the implementation plan, not an architectural
  concern), never stored or logged in plaintext or reversibly.
- Tokens: short-lived access token + refresh token, matching standard JWT
  practice for a system with no existing session-store infrastructure to
  reuse. Signing secret sourced from `EnvSettings` (`RADAR_EYE_` prefix,
  environment-only per `config.py`'s existing, established rule — never
  `configs/settings.yaml`), consistent with how `encryption_key`/DB
  credentials are already handled.
- Enforcement: a `Depends()`-based auth dependency per route, checking a
  decoded token's `role` claim against a route-declared minimum role.
- **This is a proposed design, not a mandate.** No ADR or `CLAUDE.md` text
  specifies JWT specifically — `TASKS.md`'s RE-205 backlog item claims
  `CLAUDE.md` specifies "JWT + RBAC," but this was checked directly against
  `CLAUDE.md`'s actual text and **no such statement exists there** (flagged
  here rather than silently repeated, consistent with this repository's own
  evidence-over-assumption discipline). JWT is chosen here because it fits
  ADR-009's "local users now, LDAP later" trajectory without inventing a
  session store this system doesn't otherwise need — not because anything
  mandates it. If the Principal Engineer prefers a different mechanism
  (opaque server-side session tokens, for instance), that's a one-line
  change to this section before implementation begins.

**Open question requiring explicit confirmation before implementation:**
the role taxonomy itself. `docs/OPEN_QUESTIONS.md` has this as an
unresolved, client-owned question ("What user roles are required beyond
Administrator and Operator?"). This document proposes exactly three roles —
`admin`, `operator`, `viewer` — as the minimum set implied by
`FRONTEND_BACKEND_CONTRACTS.md`'s own screens (Settings/user management
needs an administrative tier; Threat Review Center's confirm/escalate/
dismiss actions need an operational tier; read-only dashboards need a
viewer tier) — but this is this document's own proposal, not a ratified
answer to the open question, and should be confirmed explicitly rather than
implemented on the assumption it's already settled.

### 3.3 Audit logging

**Decision proposed for approval:** a new `audit_log` table, distinct from
`system_events` (operational/system-generated) and `incident_events`
(incident-lifecycle-specific) — audit records are specifically about *user*
actions (who did what, when), which neither existing table represents.
Minimum fields: `id`, `actor_user_id`, `action`, `resource_type`,
`resource_id`, `timestamp`, matching `docs/DOMAIN_MODEL.md`'s conceptual
`Audit Log` entity (`audit_id`, `timestamp`, `actor`, `action`).

An `AuditLogger` collaborator, constructed in `main.py`'s `create_app()`
and stashed on `app.state` (mirroring `HealthCollector`'s exact existing
pattern), called explicitly from mutating routes (`PATCH`/`POST` — reviews'
confirm/escalate/dismiss actions, camera/config/user updates, calibration
actions) to record the acting user and action. Read-only `GET` routes are
not audited (matching `docs/FUNCTIONAL_DECOMPOSITION.md`'s F-007 framing of
audit as capturing actions, not reads).

### 3.4 WebSocket bridge

Each `/ws/*` channel in `FRONTEND_BACKEND_CONTRACTS.md` is a thin adapter:
on client connect, `EventBus.subscribe(event_type, handler)` for that
channel's event type(s); the handler translates the internal
`EventEnvelope[Payload]` into the matching frontend schema (already built —
see §2) and sends it over the WebSocket connection; on disconnect,
`EventBus.unsubscribe()`.

**Accepted limitation, stated explicitly rather than silently inherited:**
`InProcessEventBus` delivery is best-effort/at-most-once per subscriber,
with no durable log or replay (verified against `shared/events/bus.py`'s
own design). A WebSocket client that is briefly disconnected (network
blip, browser tab backgrounded) misses whatever events published during
that gap — there is no "catch-up" mechanism. This is consistent with
`FRONTEND_BACKEND_CONTRACTS.md`'s own architecture constraint ("WebSocket
for real-time events... reduce latency") — real-time push, not a
guaranteed-delivery log — but is called out here so it's a known, accepted
trade-off rather than a gap discovered later. If gapless delivery is
required, that's a larger change (a durable event log) out of RM-12's
scope and not proposed here.

**Alert latency ≤2s acceptance criterion:** achievable directly from this
design — `EventBus.publish()`'s default `publish_timeout_seconds=1.0`
already bounds queue-wait time, and translation + WebSocket send is
in-process, sub-millisecond work. The WebSocket end-to-end latency test
(§ testing, implementation plan) measures publish-to-client-receive
directly rather than assuming this holds.

### 3.5 Response envelope

Reuse `shared/schemas/api.py`'s existing `ApiResponse[T]` for every REST
response — already the pattern `health.py` uses, already matches
`FRONTEND_BACKEND_CONTRACTS.md`'s `{"success": true, "data": {}}` contract
exactly. No new envelope design needed.

---

## 4. Non-Goals (explicitly out of scope for RM-12)

- LDAP/Active Directory integration (ADR-009's Future State — local users
  only for now).
- A durable/replayable event log for the WebSocket bridge (§3.4).
- Redesigning `system_events`/`incident_events` — `audit_log` is additive,
  not a replacement.
- Full analytics computation engine — the `/analytics/*` endpoints return
  data queryable from existing tables; anything requiring new aggregation
  infrastructure beyond straightforward repository queries is a candidate
  for its own follow-up, not silently expanded into RM-12.
- Resolving the `/api/v1` prefix question — follows RM-09's existing
  precedent (no prefix), does not re-litigate it.
- Any DeepStream/pipeline/visualization code — RM-12 is `apps/api` only.

---

## 5. Risks

- **Role taxonomy is a proposal, not a ratified decision** (§3.2) — if
  approved without confirming this explicitly, RM-12 risks building
  enforcement against a taxonomy that later needs reworking once the real
  client answer to `docs/OPEN_QUESTIONS.md`'s open item arrives.
- **No existing test/mocking pattern for JWT auth in this codebase** —
  every existing `apps/api` test hits real routes with no auth dependency
  yet; adding auth means every existing + new route test needs an
  authenticated-client fixture, a real (if small) testing-infrastructure
  addition the implementation plan must account for explicitly.
- **WebSocket testing infrastructure is greenfield** — no WS test pattern
  exists in this repo yet (`grep` confirmed zero WebSocket code anywhere).
  The "WebSocket end-to-end latency test" acceptance criterion needs a new
  test harness, not an extension of an existing one.
