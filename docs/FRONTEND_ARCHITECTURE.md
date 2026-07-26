# Radar Eye Command — Frontend Architecture

**Status:** RM-13 Phase 2 (Existing-Screen Migration) complete pending
review — Camera Management, AI Analytics, System Health, and Incident
Center migrated; Live Monitoring and Tactical Map remain on mock data,
scoped for a later phase. Builds on Phase 0 (Architecture Setup, approved)
and Phase 1 (Infrastructure, approved). This document is the reference
architecture for this milestone and every frontend milestone after it. It
describes the *target* production architecture; where Phase 0 has only
defined an interface or written a design-only piece, that's stated
explicitly rather than implied as done.

**Relationship to the prototype:** the pre-RM-13 codebase (Lovable-generated,
see `AGENTS.md`) is treated as a **visual/UX reference only** — layout,
navigation, interaction design, and visual styling are the parts of it worth
preserving. Its internal data flow (direct `mock-data.ts` imports, ad hoc
per-route mock arrays, a 3-level `1|2|3` threat model) is not architecture
and is being replaced entirely by what's described here. Where backend
reality and prototype assumptions disagree, the backend wins — see
`docs/RM-12_ARCHITECTURE.md` and `docs/FRONTEND_BACKEND_CONTRACTS.md` in the
`Radar-Eye` backend repository, which remain the authoritative sources for
every data shape and endpoint referenced below.

---

## 1. Module boundaries

```
src/
  api/           Transport layer. The ONLY code allowed to call fetch().
    generated/     openapi-typescript output (Phase 1). Read-only — never
                   hand-edited. If a generated type is wrong, the fix is a
                   backend contract change, not an edit here.
    client.ts      ApiClient — auth, correlation ID, timeout, cancellation,
                   retry, error/response normalization. (Phase 0: written.)
    endpoints/     Thin per-domain functions (cameras.ts, incidents.ts, …)
                   calling client.ts, returning generated DTOs. (Phase 1.)

  domain/
    models/        Domain models — DTOs mapped into real classes carrying
                    business behavior (§6). (Phase 0: Incident, ThreatAssessment,
                    Camera written as the reference examples; the rest follow
                    the same pattern in Phase 1/2 as each domain is migrated.)
    mappers/        DTO → domain model, one file per domain. (Phase 1+.)

  queries/          TanStack Query hooks — the only place components touch
                    server state. Built on endpoints/ + mappers/.
    queryKeys.ts    Centralized Query Key Factory. (Phase 0: written.)

  ws/               WebSocket layer. connection.ts (manager) + hooks.ts
                    (per-channel hooks that write into the Query cache).
                    (Phase 1.)

  auth/             AuthProvider, ProtectedRoute, usePermission. (Phase 1.)

  video/
    VideoProvider.ts            Interface + capability flags. (Phase 0: written.)
    PlaceholderVideoProvider.ts The only concrete implementation today.
                                (Phase 0: written.)

  features/         One folder per screen (business capability), each owning
                    only its own components/ hooks/ view-models/ utils/.
                    Cross-feature imports are avoided — shared code is
                    promoted to shared/ instead (§9).

  components/
    ui/               Unchanged from the prototype (shadcn/Radix primitives).
    hud/               Kept and extended (CameraTile, Panel, StatTile, …).
    shared/            New: ErrorBoundary, loading/empty states — used by
                       more than one feature.

  routes/            Thin — a route file defines the route and renders its
                    feature's top-level component. No business logic here.
```

**Rule:** `domain/` never imports from `api/generated/` outside its own
`mappers/`. `features/` never imports `api/` or `domain/` directly except
through `queries/`. `queries/` never imports `ws/` (the dependency runs the
other way: `ws/` writes into `queries/`'s cache via `queryClient`).

---

## 2. Data flow (end to end)

```
Backend (Radar-Eye)
  │  REST: ApiResponse<T> envelope           WS: EventEnvelope<Payload>
  ▼                                            ▼
api/generated/*.ts (OpenAPI DTO)           ws/hooks.ts (raw message)
  │                                            │
  ▼                                            ▼
domain/mappers/*.ts  ─────────────────────────►│  (same mapper — one DTO shape
  │                                                per domain, whichever
  ▼                                                transport produced it)
domain/models/*.ts (business behavior)
  │
  ▼
queries/*.ts (TanStack Query cache — single source of truth for server state)
  │
  ▼
features/*/view-models/*.ts (screen-ready shapes: formatted dates, sorted/
  │                          grouped lists, display strings — derived from
  │                          domain models, never re-deriving business rules)
  ▼
features/*/components/*.tsx → JSX
```

No component reads `api/generated/` types directly. No component computes a
date format, a status color, or a permission check inline — those are domain
model methods or view-model fields, never JSX-local logic (§7).

---

## 3. Authentication flow

**Token storage: `localStorage`.** Decision and rationale (recorded here per
architecture review):

- The backend contract (RM-12, frozen except review-driven fixes) already
  returns tokens in the JSON response body for the client to store and
  attach itself — this requires no backend change.
- `httpOnly` cookies are the stronger security posture but would require
  RM-12 to `Set-Cookie` on `/auth/login`/`/auth/refresh` and would introduce
  CSRF exposure that doesn't exist today — out of scope while RM-12 is frozen.
- Deployment context narrows the realistic risk: air-gapped (no remote
  attacker path in), single-tenant, operator-facing C2 tool, not a public
  web app.
- `sessionStorage` and in-memory storage were rejected on operational
  grounds specific to this deployment: a 24/7 watch-room display should not
  force re-login on every tab reload, and `localStorage` is the only option
  that both survives reloads and shares a session across multiple tabs/
  monitors, a real usage pattern for a command-center UI.
- Access tokens are short-lived (900s) already, bounding exposure if leaked.
  Refresh-token rotation on `/auth/refresh` should be confirmed against
  actual RM-12 behavior during Phase 1 as a companion hardening measure.
- **Migration path stays open:** if backend changes come back into scope,
  moving to `httpOnly` cookies only touches `AuthProvider`/`ApiClient`'s
  config, not `features/` or `domain/` — nothing above the API layer knows
  how the token is stored.

**Flow:**
```
User submits login form
  → POST /auth/login (via api/endpoints/auth.ts)
  → { access_token, refresh_token } stored in localStorage
  → AuthProvider context updates → ProtectedRoute allows navigation

Every subsequent request
  → ApiClient.getAuthToken() reads localStorage → Authorization: Bearer header

Access token expires (or any request returns 401 with a token present)
  → ApiClient.onUnauthorized() fires
  → AuthProvider attempts POST /auth/refresh using the stored refresh token
  → success: new tokens stored, original request's caller retries
  → failure: tokens cleared, redirect to /login

WebSocket connections
  → token passed as ?token= query param (browsers cannot set custom
    headers on the WS handshake — this is RM-12's own existing scheme,
    not something the frontend invents)
```

---

## 4. Request lifecycle (`ApiClient.request()`)

```
1. Generate a request ID (crypto.randomUUID()) — sent as X-Request-Id.
2. hooks.onRequestStart (no-op today; metrics/tracing/telemetry seam).
3. Build headers: Content-Type, X-Request-Id, Authorization (if a token exists).
4. Race the fetch against a per-request timeout (default 10s) using a
   combined AbortSignal — the caller's own signal (e.g. TanStack Query's
   queryFn signal) is honored simultaneously, whichever fires first wins.
5. Parse the ApiResponse<T> envelope.
   - Transport/parse failure → AppError("network_error").
   - HTTP !ok or envelope.success === false → AppError(envelope.error.code, …).
   - 401 specifically → config.onUnauthorized() fires, no retry.
6. GET requests with retry:true retry up to 3 attempts on failure (excluding
   401). POST/PATCH/DELETE never auto-retry — not safe to replay blindly.
7. hooks.onRequestEnd (success|error) — same seam as step 2.
8. Return envelope.data, or throw the normalized AppError.
```

Downloads (`GET /recordings/{id}/download`, `GET /snapshots/{id}/download`)
use `ApiClient.requestBlob()` instead — those endpoints return the raw file,
not an `ApiResponse` envelope.

---

## 5. WebSocket lifecycle

```
Screen mounts → ws/hooks.ts's useXChannel() calls ws/connection.ts.connect(channel, token)
  → on open: nothing else happens yet — REST queries already established
    baseline state via queries/*.ts on mount (REST first, WS incremental,
    per the architecture review's explicit rule)
  → on message: map the raw payload through the SAME domain/mappers/*.ts
    used by REST, then:
      - if it can be merged safely into the existing cache entry
        → queryClient.setQueryData(matching key, updater)
      - if it cannot be merged safely
        → queryClient.invalidateQueries({ queryKey: matching key })
        (correctness over cleverness — an incremental update is only
        applied when it's unambiguous how to merge it; anything else
        triggers a real refetch)
  → on disconnect: connection.ts backs off and reconnects; on reconnect,
    re-subscribes to the same channel (no separate re-fetch needed — an
    open reconnect gap is exactly what a REST re-fetch on remount /
    window-focus already covers via TanStack Query's own defaults)
Screen unmounts → disconnect(channel)
```

There is never a second, WS-only store. `ws/` writes exclusively into the
same `queryClient` cache `queries/` populates — a component subscribed via
`useIncidentsQuery()` sees both the initial REST fetch and every live WS
update through one cache entry.

---

## 6. DTO → Domain → ViewModel transformation

```
OpenAPI DTO (generated/, transport shape, matches the backend 1:1)
   │  mapper (domain/mappers/incident.ts)
   ▼
Domain Model (domain/models/Incident.ts — a real class: readonly fields +
   │           business-behavior methods, e.g. canAcknowledge()/canClose().
   │           These methods drive UI affordances only; the backend
   │           re-validates every mutation regardless of what the UI shows.)
   │  selector (features/incidents/view-models/incidentRow.ts)
   ▼
View Model (screen-ready: formatted timestamp, resolved display color via
   │         the domain model's own displayColor(), pre-joined camera name —
   │         never re-implements a business rule the domain model already owns)
   ▼
React Component (renders the view model — no date formatting, no status
             mapping, no color logic inline in JSX)
```

Phase 0 delivered three worked examples of the DTO→Domain step —
`Incident`, `ThreatAssessment`, `Camera` (`src/domain/models/`) — establishing
the pattern before it's replicated for Review, CameraCalibration, Evidence,
and User during Phase 1/2's actual screen migrations.

---

## 7. Query lifecycle

- `queryKeys.ts` (§1) is the only source of query key arrays — never a
  literal `["incidents", id]` inline in a hook or component.
- Query hooks live in `queries/`, one module per REST domain, built on
  `api/endpoints/` + `domain/mappers/`.
- `staleTime`/`gcTime` are set per data class, not globally: live-feed data
  (threats, incidents) relies on WS for freshness and can have a longer
  `staleTime` since WS keeps it current; reference data (cameras, users)
  can cache longer still; analytics aggregates longest.
- React component state (`useState`/`useReducer`) holds **only** transient
  UI state — selected tab, open dialog, form draft. Server data never lives
  in component state; if a component needs server data, it calls a
  `queries/` hook, full stop.
- Mutations (`useMutation`) call `api/endpoints/`, then either update the
  cache optimistically where safe or `invalidateQueries()` — same
  correctness-over-cleverness rule as WS (§5).

---

## 8. VideoProvider abstraction

See `src/video/VideoProvider.ts` (interface, Phase 0) and
`PlaceholderVideoProvider.ts` (Phase 0's only implementation). `CameraTile`
depends on the `VideoProvider` interface only; it never imports a concrete
provider class. Capability flags (`supportsLiveVideo()`,
`supportsSnapshots()`, `supportsRecordingPlayback()`) let a component ask
"can the active provider do X" instead of assuming — a future
`RTSPProvider`/`WebRTCProvider`/`HLSProvider` implements the same interface
and simply advertises real capability, with zero change required in
`CameraTile` or any feature that consumes it.

**Open backend dependency, not resolved by this abstraction:** no live
video delivery mechanism or contract exists yet (`ADR-011` mandates
"backend-controlled video delivery," but no endpoint/URL scheme is defined
in `FRONTEND_BACKEND_CONTRACTS.md`, and the backend's `ThreatAssessmentEvent`
carries no bounding-box coordinates for the detection-overlay feature
either). This is real, separate work spanning `apps/deepstream` and
`apps/api` in the backend repo — the `VideoProvider` seam exists so that
work can land later without touching this codebase's screens again.

---

## 9. Feature boundaries

Each `features/<name>/` folder owns only code specific to that screen:
`components/`, `hooks/` (screen-specific query/mutation wrappers, if any
beyond the shared `queries/` hooks), `view-models/`, `utils/`. Anything a
second feature needs is promoted to `components/shared/`, `domain/`, or
`queries/` — never imported cross-feature directly. If two features start
needing the same thing, that's the signal to promote it, not to import
across the feature boundary.

Planned features (§ RM-13 scope): `live-monitoring`, `incidents`,
`tactical-map`, `cameras`, `analytics`, `health`, `settings`,
`threat-review` (new), `calibration` (new), `evidence` (new), `auth` (new).

---

## 10. Known open items (tracked, not resolved by Phase 0)

| Item | Owner | Status |
|---|---|---|
| CORS policy on `apps/api` | Backend | Not yet configured — needed before any real integration testing |
| `GET /audit-log`-equivalent endpoint | Backend | Doesn't exist; `audit_log` table does (RM-12 Phase 2) |
| Live video delivery contract | Backend (`apps/deepstream` + `apps/api`) | No contract; `VideoProvider` seam is ready for it |
| `/ws/tracking` | Backend | Explicitly deferred (`docs/OPEN_QUESTIONS.md` Q-015) |
| AI Model / Notifications settings tabs | Backend (Configuration Service) | Explicitly deferred (`docs/OPEN_QUESTIONS.md` Q-014) — rendered as an explicit disabled state, not removed |
| Refresh-token rotation | Backend | Assumed present, not yet confirmed against actual RM-12 behavior |

---

## 11. Pre-Phase-1 pipeline validation

Performed before any Phase 1 code was written, per Phase 0 review. Checks
every planned feature against: generated DTO → mapper → domain model →
query → WebSocket event (if applicable) → feature module. Four domains
required an explicit architectural decision rather than a straight
pass-through; each is recorded here so the decision is traceable, not
silently made during implementation.

| Domain | DTO | Mapper | Domain model | Query | WS | Feature module | Result |
|---|---|---|---|---|---|---|---|
| Cameras | `CameraSchema` (RM-12) | needed, not yet written | `Camera` (Phase 0) | `queryKeys.cameras.*` | `/ws/camera-health` | `features/cameras` | Fits cleanly |
| Threats | `ThreatAssessmentSchema` | needed | `ThreatAssessment` (Phase 0) | `queryKeys.threats.*` | `/ws/threats` | `features/live-monitoring` | Fits cleanly |
| Incidents | `IncidentSchema` | needed | `Incident` (Phase 0) | `queryKeys.incidents.*` | `/ws/incidents` | `features/incidents` | Fits cleanly |
| Tactical map | reuses Cameras/Threats/Incidents | reuses existing | reuses existing | reuses existing | reuses existing | `features/tactical-map` | Fits cleanly — no new domain. Known gaps (no `/ws/tracking`, no camera lat/lng in `CameraSchema`) are already tracked in §10, not new findings |
| Reviews | `HumanReviewItemSchema` | needed | new `HumanReviewItem` domain model | `queryKeys.reviews.*` | `/ws/reviews` (creation only) | `features/threat-review` (new) | **Gap found — see below** |
| Calibration | `CalibrationResultSchema` | needed | new `CalibrationResult` domain model | `queryKeys.calibration.*` | none (by design) | `features/calibration` (new) | Fits — no WS channel is correct, not a gap: calibration is an infrequent, on-demand operator workflow |
| Evidence | `RecordingSchema`/`SnapshotSchema` | needed | new `Evidence` domain model | `queryKeys.evidence.*` | none (by design) | `features/evidence` (new) | Fits — same reasoning as Calibration |
| Analytics | aggregate report DTOs | needed | **exception — see below** | `queryKeys.analytics.*` | none (by design) | `features/analytics` | Intentional pipeline exception |
| Health (GPU/CPU/storage) | `SystemHealthSchema` | needed | thin/pass-through (same exception as Analytics) | `queryKeys.health.*` | **Gap found — see below** | `features/health` | REST-polling exception |
| Users / Settings | `UserSchema` | needed | new `User` domain model | `queryKeys.users.*` | none | `features/settings` | Fits — one open design question, not a gap, see below |
| Auth | login/token DTOs | needed | no domain model needed (token is not a business entity) | not a TanStack Query concern — held in `AuthProvider` | none | `features/auth` (new) | Fits |

**Finding 1 — Reviews: no resolution-event WS channel.** `/ws/reviews`
carries `HumanReviewItemCreatedEvent` only (RM-12 Phase 5 scope). There is
no backend event for a review item being resolved/escalated/dismissed, so
a second operator's browser will not get a live push when someone else
resolves a review item — only the acting client's own REST response
updates their own view. This is a real gap, but not one Phase 0/1
architecture needs to solve: it is a Phase 3 (`features/threat-review`)
implementation decision. Mitigation recorded here so it isn't rediscovered
later: give the reviews list query a short `staleTime` and
`refetchOnWindowFocus: true` rather than treating it as WS-driven like
Incidents/Threats. Not a blocker for Phase 1.

**Finding 2 — Health: no WS channel for periodic metrics.**
`/ws/camera-health` carries `CameraDisconnectedEvent`/`SystemEvent`
(discrete events), not periodic GPU/CPU/storage telemetry. The System
Health screen's metric widgets have no event source to subscribe to and
must use REST polling (a bounded `refetchInterval` on the query). This is
in tension with `FRONTEND_BACKEND_CONTRACTS.md`'s "avoid polling where
practical" principle, but is a reasonable, documented exception — the
data is genuinely poll-shaped (a periodic gauge, not a discrete event) and
no backend event stream exists for it. Recorded here, not silently
implemented in Phase 3 as if it were the default pattern.

**Finding 3 — Analytics / Health: pass-through domain model is correct,
not a violation.** The `DTO → Domain (business behavior) → ViewModel`
pattern assumes a domain entity with behavior worth modeling
(`Incident.canAcknowledge()`, `ThreatAssessment.requiresImmediateAction()`,
etc.). Analytics and health-metrics data is pure aggregate/reporting
output with no business behavior to express — inventing methods on an
`AnalyticsSummary` class to satisfy the pattern would be exactly the kind
of fabricated capability the Phase 0 review warned against
(`canEscalate()` precedent). For these two domains only, the mapper may
produce a thin pass-through object (or the view model directly), skipping
a behavior-bearing domain model. This is an intentional, narrow exception,
not a gap in the pipeline design.

**Finding 4 — Users: role-check placement is a design question, not a
gap.** Whether `hasRole()`/permission-check logic belongs on a `User`
domain model or purely inside the `usePermission()` hook is undecided.
Both fit the pipeline; this is deferred to Phase 2 as an implementation
detail, not an architectural blocker.

**Conclusion:** every planned domain maps to the DTO → mapper → domain →
query → (WS) → feature pipeline. No domain requires a pipeline redesign.
Two real, backend-driven gaps were found (Reviews resolution events,
Health metric events) and are recorded as scoped implementation
exceptions rather than blockers. Phase 1 may proceed.

---

## 12. Domain facts vs. authorization (resolved before Phase 2)

Rule, decided before any Phase 2 code: **domain models expose facts;
authorization decisions belong to the auth layer, never to a domain
model.**

- `Incident.canAcknowledge()` / `.canClose()` / `.isTerminal()` (Phase 0)
  are *not* an exception to this rule — they encode backend-enforced
  **business state transitions** (`EXTERNALLY_REQUESTABLE_TRANSITIONS`),
  the same fact for every caller regardless of who's asking. They answer
  "is this incident in a state where X is possible," not "is *this user*
  allowed to do X."
- Authorization — "can *this* user do X" — is a function of the current
  user's role, not of the entity being acted on. It belongs exclusively in
  `usePermission()` (`src/auth/usePermission.ts`) and nowhere else. No
  domain model gets a `hasRole()`, `canEdit()`-meaning-role-gated, or
  similar method.
- Two distinct `User`-shaped types exist for two distinct purposes and
  must not be conflated:
  - `AuthUser` (`src/auth/types.ts`) — the current session's identity,
    decoded from the JWT + login input. Auth infrastructure, not a REST
    domain entity. Consumed by `AuthProvider`/`usePermission()` only.
  - `User` (`src/domain/models/User.ts`, Phase 3 — Settings/Users screen)
    — the full `UserSchema` entity (`user_id`, `username`, `role`,
    `created_at`) returned by `GET /users`, for an admin managing other
    users. Exposes `role` as a plain fact (`readonly role: string`); it
    does **not** get a `hasRole()` method, including for the admin's own
    authorization checks against list rows — that composition still goes
    through `usePermission()` at the call site (e.g. "does the *current
    operator* have permission to edit *this listed user's* role" is two
    facts — `usePermission("admin")` and the target row's `user.role` —
    combined in the component/view model, not fused into the entity).

UI components combine both: `usePermission()` answers "is the current
operator allowed," a domain model's own methods (if any) answer "is this
action possible given the entity's state." A role-gated mutation button
checks both independently and never encodes the role check inside the
entity.

---

## 13. Technical debt: WebSocket contracts are not generated

Tracked here per Phase 1 review — explicitly **not** solved during RM-13.
A future infrastructure milestone's job, not this one's.

**Current state:** `src/ws/messages.ts` hand-declares every `/ws/*`
message shape (`ThreatAssessmentMessage` reuses the generated
`ActiveThreatSchema` where a REST-exposed twin exists; `ReviewMessage`
reuses generated `HumanReviewSchema` likewise; `IncidentCreatedMessage`,
`IncidentUpdatedMessage`, `CameraDisconnectedMessage`, `SystemEventMessage`,
`AlarmMessage` are fully hand-typed, with no REST-exposed twin at all).
Two of the five channels (`incidents`, `camera_health`) additionally carry
more than one message shape with no on-the-wire discriminator field,
requiring structural type guards (`isIncidentUpdatedMessage`,
`isSystemEventMessage`) instead of a tagged union.

**Source of truth:** `shared/schemas/*.py` in the `Radar-Eye` backend repo
— specifically the classes cited in each type's docstring in
`src/ws/messages.ts`. FastAPI's `.openapi()` output (what
`openapi-typescript` consumes for the REST layer) has no WebSocket
representation at all — this isn't a gap in how the schema was exported,
it's a structural limit of OpenAPI itself, so the existing REST
type-generation pipeline cannot be pointed at it.

**Future code-generation possibilities** (not evaluated in depth, listed
for whoever picks this up):
- A small backend-side export script that introspects the WS-message
  Pydantic classes already declared in `shared/schemas/*.py` (they're
  ordinary `BaseModel` subclasses, not FastAPI-route-bound) and emits a
  JSON Schema document per channel, consumed by the same
  `openapi-typescript`-style generator already in the frontend toolchain.
- Adopting AsyncAPI as a parallel spec alongside OpenAPI, with the
  WS-bridge's `_CHANNEL_BY_EVENT_TYPE`/`_TRANSLATOR_BY_EVENT_TYPE` mapping
  (`apps/api/app/websockets/bridge.py`) as the source the spec would need
  to be generated from or kept consistent with.
- At minimum, a contract test (backend-side) asserting each translator's
  output still matches its schema's field set, so a silent backend field
  rename is caught in CI rather than discovered as a frontend runtime bug.

Until one of these exists, every change to a WS-message-shaped schema in
the backend repo must be manually mirrored in `src/ws/messages.ts` — there
is no compiler or generator that will catch drift.

---

## 14. Phase 2 migration record: prototype content vs. backend reality

Migrated: Camera Management (`routes/cameras.tsx`), AI Analytics
(`routes/analytics.tsx`), System Health (`routes/health.tsx`), Incident
Center (`routes/incidents.tsx`). Per RM-13's "backend wins" rule, each
screen's real data availability was checked against the generated OpenAPI
schema and `shared/schemas/*.py` before writing any UI, not assumed from
the prototype. Fields/panels/actions with no backing endpoint were
dropped, not fabricated or stubbed with placeholder numbers. Recorded here
because several of these are large enough departures from the prototype's
visual richness to need a permanent, findable reason, not just a commit
message.

**Cameras**: `CameraSchema`/`CameraHealthSchema` provide id/name/location/
status/fps/last_frame_age only. Dropped: health %, latency (ms), AI
on/off, recording indicator, storage used, and the entire configuration
modal's resolution/codec/confidence-threshold/detection-types/privacy-
mask/firmware fields — `CameraUpdateRequestSchema` (`PATCH /cameras/{id}`,
admin-only) supports name/location/status only.

**Analytics** — the largest departure. `shared/schemas/analytics.py`'s own
docstring: "straightforward repository-query aggregations... not a new
analytics computation engine." Real: counts by threat level, incident
totals + counts by status, top cameras by incident count, system-wide
totals. Dropped entirely (no endpoint of any kind): 24h hourly trend,
precision/recall/F1/false-positive/false-negative, response-time
percentiles, per-sector threat heatmap, weapon-frequency breakdown. GPU/
inference metrics moved to System Health, where `/health/gpu` actually is.

**System Health**: real endpoints cover GPU (nullable — honestly empty
outside NVML/Jetson hardware), evidence storage, recording storage, per-
camera health, and a fixed 5-key component-status map (database/
event_bus/gpu/storage/cameras). Dropped: CPU, memory, ambient temperature,
network uplink, MQTT broker, notification bus — no endpoint exists for any
of them, consistent with CLAUDE.md's single-Jetson-SoC deployment target
rather than the prototype's discrete-workstation assumption (RTX A6000 /
EPYC CPU labels). Event Log Stream has no backing endpoint (`GET
/audit-log` doesn't exist, §10) — shown as an explicit disabled panel,
matching Settings' existing precedent for deferred tabs.

**Incidents**: `IncidentSummarySchema`/`IncidentSchema` carry no weapon
type, no assigned operator, no confidence score, no escalation field, no
free-text location. Dropped: the "object"/"operator"/"confidence"/
"escalation" fields, the "Resolved 24h"/"Avg. Response" stats (no time-
windowed aggregate exists), the fabricated response-timeline steps
(replaced with real `GET /incidents/{id}/events`), and the Assign/Export
actions (no backend support; Export belongs to the future Evidence
feature). Added: real Acknowledge/Resolve actions via `PATCH
/incidents/{id}`, gated by both `Incident.canAcknowledge()`/`.canClose()`
(state fact) and `usePermission("operator")` (authorization) per §12.

**Mid-phase architecture refinement**: Phase 0's `Incident` domain model
required all of track_id/incident_type/created_at/updated_at, but the list
endpoints (`GET /incidents`, `GET /incidents/open`) return
`IncidentSummarySchema` (id/camera_id/threat_level/status only) — a real
DTO-shape mismatch Phase 0 didn't anticipate. Resolved by extracting the
transition-check predicates into `domain/incidentStatus.ts` (pure
functions) and adding `IncidentSummary` (`domain/models/IncidentSummary.ts`)
as a list-context companion to `Incident`, both delegating to the same
functions rather than one being constructed from the other's incomplete
data. The equivalent `ThreatLevel` label/color mapping was extracted from
`ThreatAssessment` into `domain/threatLevel.ts` the same way, since
`Incident`/`IncidentSummary` needed it too and duplicating the switch
statement would have violated "the ONLY place this mapping should exist."
