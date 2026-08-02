# Frontend Architecture Review

**Status:** As-built reference, post-RM-13. Describes the production
frontend architecture as it exists today, not its history — for the
phase-by-phase migration record (what changed, why, and what was removed
along the way), see `RM-13_MIGRATION_SUMMARY.md`. For the original
phase-journal document this was distilled from, see
`FRONTEND_ARCHITECTURE.md`, which remains the authoritative source for
anything not repeated here.

---

## 1. Final directory structure

```
src/
  api/
    client.ts              ApiClient — the only module that calls fetch()
    instance.ts             composition root: wires ApiClient to auth/tokenStore
    types.ts / AppError.ts  transport envelope types, normalized error type
    endpoints/               one module per REST domain (auth, cameras, threats,
                              incidents, reviews, calibration, evidence, analytics,
                              health, users) — thin wrappers over apiClient.request()
    generated/
      schema.d.ts             openapi-typescript output — read-only, regenerated
                               from the backend's live OpenAPI schema, never
                               hand-edited

  auth/
    tokenStore.ts            SSR-safe token storage (localStorage), pub/sub
    session.ts                login/logout/refresh orchestration (non-React)
    jwt.ts                    client-side JWT payload decode (no verification)
    types.ts                  AuthUser, ROLE_RANK
    AuthProvider.tsx          React context, proactive refresh scheduling
    RouteGuard.tsx             client-side auth enforcement
    usePermission.ts          role-rank authorization hook

  domain/
    models/                   one class per REST/business entity: Camera,
                              ThreatAssessment, Incident, IncidentSummary,
                              HumanReviewItem, CameraCalibration, Evidence, User
    mappers/                  one function per entity: DTO -> domain model
    threatLevel.ts             shared ThreatLevel type + label/color mapping
    incidentStatus.ts          shared IncidentStatus type + transition predicates

  queries/
    queryKeys.ts               centralized query key factory, one namespace per
                              REST domain
    staleTimes.ts               per-data-class staleTime tiers
    useCameras.ts / useThreats.ts   shared, cross-feature REST-domain query hooks

  features/
    <name>/hooks/               feature-scoped query/mutation hooks (built on
                              api/endpoints + domain/mappers)
    <name>/view-models/         DTO/domain -> display-ready shape, joins,
                              filters, aggregation
    (cameras, analytics, health, incidents, reviews, calibration, evidence,
     settings)

  components/
    shared/                    cross-feature UI: ThreatLevelBadge, QueryState
                              (Loading/Empty/Error), DisabledFeaturePanel,
                              LiveCameraTile
    hud/                       visual-language primitives inherited from the
                              Lovable prototype (Panel, StatTile, Bar)
    ui/                        shadcn primitives (unmodified)

  video/
    VideoProvider.ts            interface + capability flags
    PlaceholderVideoProvider.ts  the only implementation today
    VideoProviderContext.tsx    React context + useVideoHandle() hook

  ws/
    connection.ts               WebSocket channel manager (lazy connect,
                              reconnect, token-aware)
    messages.ts                 hand-typed WS message shapes + structural
                              type guards (WS has no OpenAPI coverage)

  routes/                      one file per screen (TanStack Router,
                              file-based), + __root.tsx (shell, nav, auth/
                              video provider wiring) and login.tsx
  router.tsx                   QueryClient construction + defaults
```

---

## 2. Architectural layers

```
Transport DTO  →  Mapper  →  Domain Model  →  View Model  →  UI
```

- **Transport DTO** (`api/generated/schema.d.ts`): generated from the
  backend's live OpenAPI schema via `openapi-typescript`. Read-only,
  disposable, regenerated on backend contract change — never patched or
  extended by hand. The one documented exception is WebSocket message
  shapes (`ws/messages.ts`), which have no OpenAPI representation at all
  and are hand-typed against `shared/schemas/*.py` in the backend repo.
- **Mapper** (`domain/mappers/*.ts`): one pure function per entity,
  `dto -> domain model`. No business logic, no formatting — field mapping
  only.
- **Domain Model** (`domain/models/*.ts`): a class per business entity,
  exposing real business-behavior methods where the backend enforces real
  rules (e.g. `Incident.canAcknowledge()`, mirroring
  `EXTERNALLY_REQUESTABLE_TRANSITIONS`), and *facts only* — never
  authorization — per the resolved rule in §9 below. Two domains
  (Analytics, Health) are a documented pass-through exception: pure
  aggregate/reporting data with no business behavior to model.
- **View Model** (`features/*/view-models/*.ts`): joins domain entities
  with cross-domain display data (e.g. resolving a camera name for an
  incident row), computes derived display state (status counts, filtered/
  sorted lists), and shapes data for direct UI consumption. Never talks to
  the network.
- **UI** (`routes/*.tsx`, `components/`): presentation only. Calls a
  `features/*/hooks/` query hook, renders the view model it returns,
  handles loading/empty/error states via the shared `QueryState`
  components, and gates mutating actions with `usePermission()` plus the
  relevant domain fact (e.g. `incident.canClose()`).

No screen skips a layer. No component imports `api/generated/schema.d.ts`
directly.

---

## 3. Request lifecycle (`ApiClient.request()`)

1. Caller (a `features/*/hooks/` query/mutation function via
   `api/endpoints/*.ts`) invokes `apiClient.request<T>(path, options)`.
2. A request correlation ID (`crypto.randomUUID()`) is generated and
   attached as `X-Request-Id`.
3. Auth header injection: `getAuthToken()` (wired to `tokenStore` in
   `api/instance.ts`) supplies the bearer token, if present.
4. A per-request timeout races the fetch via a combined `AbortSignal`
   (caller-supplied signal + internal timeout controller).
5. Idempotent GET requests retry up to 3 attempts; mutations
   (POST/PATCH/DELETE) never auto-retry.
6. Response parsing: the `ApiResponse<T>` envelope
   (`{success, data, error}`) is unwrapped; failures normalize into one
   `AppError` type (`code`, `httpStatus`, `requestId`, `isUnauthorized`/
   `isForbidden`/`isNotFound` getters) regardless of whether the failure
   was a network error, an HTTP error, or an `ApiResponse.error` payload.
7. A 401 on a request that carried a token triggers `onUnauthorized()`
   (wired to force-logout via `tokenStore.clearTokens()`), never a
   silent retry.
8. File-download endpoints (`/recordings/{id}/download`,
   `/snapshots/{id}/download`) go through `requestBlob()` instead —
   same auth/correlation-ID/timeout handling, but the raw file is
   returned, not an `ApiResponse` envelope.

`ApiClient` has zero import-time dependency on `auth/` — `api/instance.ts`
is the one composition root that wires the two together, keeping the
client independently testable.

---

## 4. WebSocket lifecycle

One shared `WebSocket` connection per channel (`threats`, `incidents`,
`camera_health`, `reviews`, `alarms`), managed by `ws/connection.ts`:

1. Opens lazily on the first `subscribeToChannel()` call for a channel;
   multiple subscribers share one underlying socket (mirrors the
   backend's own "one `EventBus` subscription per event type, not per
   connection" design).
2. Auth: the access token is passed as `?token=` on the handshake URL
   (the one place a browser WebSocket can carry it) — matches the
   backend's `_authenticate()` exactly.
3. Reacts to `tokenStore` changes: a cleared token (logout, forced
   logout) closes the connection immediately; a new token reopens it if
   there are still active subscribers.
4. Reconnects with exponential backoff (1s → 30s cap) on unexpected
   close.
5. On message: parsed, then handed to every subscriber's handler.
   Two channels (`incidents`, `camera_health`) carry more than one
   message shape with no discriminator field on the wire — resolved via
   structural type guards in `ws/messages.ts`
   (`isIncidentUpdatedMessage`, `isSystemEventMessage`).
6. Every WS-consuming query hook's handler **invalidates** the relevant
   TanStack Query cache entries rather than attempting a partial merge —
   the deliberate, consistently-applied tradeoff across the whole
   codebase (see §7). WS never writes into a second, parallel store.

---

## 5. Authentication lifecycle

1. **Token storage** (`auth/tokenStore.ts`): SSR-safe — starts every
   render (server and first client render) as "not hydrated"; reads
   `localStorage` once, client-side only, after mount. Not React —
   both `AuthProvider` and `api/instance.ts`'s composition root depend on
   it as the single source of truth, so there's never a React-state copy
   that can drift from `localStorage`.
2. **Login**: `AuthProvider.login()` → `auth/session.ts::loginWithCredentials()`
   → `POST /auth/login` → tokens stored (access + refresh + the typed
   username, since there is no `GET /auth/me` and the JWT payload carries
   no username — see the Backend Capability Gap Register).
3. **Session identity**: the access token's JWT payload (`sub`, `role`,
   `exp`) is decoded client-side (no signature verification — the backend
   is the sole verification authority) to reconstruct `AuthUser`.
4. **Proactive refresh**: `AuthProvider` schedules a refresh ~60s before
   the access token's own `exp`, calling `POST /auth/refresh`. The 401
   handler in `api/instance.ts` (force-logout) is the fallback safety net
   if a request slips past an unrefreshed, expired token — not the
   primary refresh mechanism.
5. **Route protection**: `RouteGuard` wraps every route except `/login`.
   Enforcement is client-side only — TanStack Start server-renders this
   app, and the server has no access to `localStorage`, so there is no
   reliable server-side redirect available under the approved
   `localStorage` token-storage decision. `AuthProvider`'s status starts
   at `"loading"` identically on server and first client render (no
   hydration mismatch) and resolves once the client reads `tokenStore`.
6. **Authorization**: `usePermission(minimumRole)` compares the current
   user's role against `ROLE_RANK` (`viewer: 0, operator: 1, admin: 2`),
   mirroring the backend's `require_role()` fail-closed semantics exactly
   (an unrecognized role ranks below every known role). This is a UI-only
   gate — the backend's own `require_role()` is the actual enforcement.

---

## 6. Query lifecycle

- **Query Key Factory** (`queries/queryKeys.ts`): the only source of
  query key arrays. No hook or component constructs a literal key.
- **staleTime tiers** (`queries/staleTimes.ts`): set per data class, not
  globally — `liveFeed` (30s, WS-backed data), `reviews` (15s, the one
  domain with a documented WS gap), `reference` (5 min, changes only on
  operator action), `analytics` (10 min, coarse aggregates). The
  `QueryClient`'s own defaults (`router.tsx`) use the most conservative
  tier; individual hooks override per class.
- **Hook placement**: a query hook lives in `queries/` if more than one
  feature needs it (e.g. `useCameras()`, needed by both Camera Management
  and Analytics), or in `features/<name>/hooks/` if it's exclusive to one
  screen. This boundary was actively enforced during RM-13 — `useCameras`/
  `useCamerasHealth` were relocated from `features/cameras/` to
  `queries/` once Analytics needed the same data.
- **Mutations**: call `api/endpoints/`, then `invalidateQueries()` on
  success — no optimistic-update path is in use anywhere today (a
  reasonable future addition, not built speculatively).
- **Component state**: `useState`/`useReducer` holds transient UI state
  only (selected filter, open modal, form draft). Server data never
  lives in component state — a component needing server data calls a
  query hook, full stop.

---

## 7. WebSocket-to-cache strategy: invalidate, not merge

Every WS-consuming query hook in the codebase (`camera_health`,
`incidents`, `reviews`, `threats`) invalidates the relevant query on
message receipt rather than attempting a partial merge into cached data.
This was a deliberate, consistently-applied decision, not a shortcut:

- Most WS messages genuinely carry partial state (e.g. `/ws/incidents`'
  `IncidentUpdatedMessage` has no `camera_id`/`track_id` at all) — a
  merge would require either discarding fields or fabricating them.
- `/ws/threats`' messages happen to carry the *full* entity shape, where
  a merge would be technically safe — but the codebase stays consistent
  rather than making that one exception, on the principle that
  correctness-over-micro-optimization should apply uniformly, not
  case-by-case.
- The cost is one extra round-trip per WS event instead of an instant
  local update; at current scale (single node, 20 cameras) this is not
  observable in practice.

---

## 8. Video abstraction

`video/VideoProvider.ts` defines the interface (`connect()`,
`disconnect()`, three capability flags:
`supportsLiveVideo/supportsSnapshots/supportsRecordingPlayback`).
`PlaceholderVideoProvider.ts` is the only implementation today — honestly
reports zero capability rather than faking one, and `connect()` always
yields an `"unavailable"` handle. `video/VideoProviderContext.tsx`
exposes it via `useVideoProvider()`/`useVideoHandle(cameraId)`; no
component anywhere imports a concrete provider class directly. This is
the one seam a future `RTSPProvider`/`WebRTCProvider`/`HLSProvider`
plugs into without touching `LiveCameraTile`, Calibration Center, or any
other consumer.

Evidence Viewer's recording/snapshot playback is a deliberately separate
mechanism (fetching an authenticated file as a `Blob` and creating a
local object URL) — archived-file retrieval, not live video, and outside
`VideoProvider`'s scope by its own docstring.

---

## 9. Domain facts vs. authorization

Resolved before Phase 2 (originally recorded in `FRONTEND_ARCHITECTURE.md`
§12): **domain models expose facts; authorization decisions belong
exclusively to `usePermission()`.** A domain model's own methods
(`Incident.canAcknowledge()`, `HumanReviewItem.canResolve()`) answer "is
this entity in a state where X is possible" — the same answer for every
caller. "Can *this user* do X" is composed at the call site from
`usePermission(role)` plus the entity's own fact, never fused into the
entity itself. No domain model anywhere has a `hasRole()`-shaped method.

---

## 10. Feature organization

`features/<name>/{hooks,view-models}` — one folder per screen-owned
concern. A feature never imports another feature's internals directly;
anything two features need is promoted to `queries/`, `domain/`, or
`components/shared/` (this happened concretely three times: `useCameras`/
`useCamerasHealth` → `queries/`, `ThreatLevelBadge` → `components/shared/`,
`QueryState`/`DisabledFeaturePanel` → `components/shared/`).

Built features, one per REST domain: `cameras`, `analytics`, `health`,
`incidents`, `reviews`, `calibration`, `evidence`, `settings`. Live
Monitoring and Tactical Map are screens (`routes/index.tsx`,
`routes/map.tsx`) that compose *existing* feature hooks rather than
owning a feature folder of their own — deliberately, since they introduce
no new REST domain or business concept beyond what Cameras/Threats/
Incidents already model.

---

## 11. Design rationale (summary)

The architecture optimizes for one property above all others, stated
directly in `CLAUDE.md`'s RM-13 framing: **the UI must represent reality,
not prototype assumptions, and never invent backend behavior to preserve
visual density.** Every layer boundary in this document exists to make
that property mechanically enforceable rather than a matter of discipline
per screen — generated types make transport drift a compile error;
mappers/domain models/view models give every "is this real data" question
exactly one place to be answered honestly; the WS-invalidate rule and the
`VideoProvider` seam mean "we don't have this data yet" has a first-class,
non-fabricated representation instead of a silently-faked one.