# Technical Debt Register

**Status:** Frontend-owned debt only — items the frontend can resolve
without waiting on a backend change. For missing backend endpoints/
fields/events, see `BACKEND_CAPABILITY_GAPS.md`; several items below
reference a gap there as related context, but are listed here because the
frontend-side piece is independently actionable.

None of these block production use at current scale (single node, 20
cameras). Each is either a named seam already built for future
replacement, or a concrete threshold that would trigger the work.

---

## D-1. No retry-after-refresh queue for 401s

**Where:** `src/api/instance.ts`'s `onUnauthorized` callback.

Today, a 401 on a request that carried a token triggers an immediate
force-logout (`tokenStore.clearTokens()`). Proactive refresh
(`AuthProvider`, scheduled ~60s before the access token's `exp`) is the
primary mechanism and should prevent this in normal operation — the
force-logout path only fires when a request slips past an unrefreshed,
already-expired token (clock skew, a tab left idle past the refresh
timer, etc.).

**What's missing:** a request that hits this edge case is simply lost —
the user is logged out and has to re-authenticate and retry manually,
rather than the client silently refreshing and replaying the original
request.

**Why deferred:** building this correctly requires queuing concurrent
in-flight requests during a refresh (to avoid triggering N parallel
refresh calls if N requests 401 simultaneously), which is real complexity
for an edge case the proactive-refresh timer already makes rare. Noted as
a named seam in `api/client.ts`'s own docstring at the time it was built,
not an oversight.

**Trigger to fix:** repeated real-world reports of unexpected logout
during normal use (as opposed to genuine session expiry).

---

## D-2. WebSocket message contract drift has no compiler safety net

**Where:** `src/ws/messages.ts`.

Every `/ws/*` message shape is hand-typed against
`shared/schemas/*.py` in the backend repo, because FastAPI's OpenAPI
output has no WebSocket coverage at all. A backend field rename would
only surface as a frontend runtime bug.

**Frontend-side mitigation available today:** none beyond code comments
citing the exact backend class each type mirrors — this is fundamentally
a cross-repo contract problem, not something the frontend can fully solve
alone.

**Related backend gap:** `BACKEND_CAPABILITY_GAPS.md` G-4 (WS schema
generation or a contract test) — the real fix has to originate on the
backend side (exporting a schema or adding a contract test), but once
that exists, this repo's job is straightforward: point a generator at it
the same way `openapi-typescript` is already wired for REST.

---

## D-3. Client-side filtering stands in for missing server-side filters

**Where:** Evidence Viewer (`features/evidence/`), Threat Review Center
(`features/reviews/`), Camera Management's search box.

`GET /evidence`, `GET /reviews`, and `GET /cameras` all return their full
table; type/camera/status filtering happens client-side over the
complete result set. This is correct and simple at current volume, but
is a pattern that will need to change in lockstep with
`BACKEND_CAPABILITY_GAPS.md` G-5 (server-side pagination/filtering) —
listed here as the frontend-side half of that gap, since the query hooks
and view-model filter functions will need real rework (not just a
backend endpoint change) once pagination exists: `useEvidenceList()`/
`useReviews()` will need to become parameterized, paginated queries, and
`applyEvidenceFilter()`'s client-side filtering will move server-side.

**Trigger to fix:** see D-6's performance thresholds below — this is the
frontend work required once G-5 lands, not before.

---

## D-4. No streaming video provider implementation

**Where:** `src/video/`.

`VideoProvider` is a real interface with capability flags
(`supportsLiveVideo`/`supportsSnapshots`/`supportsRecordingPlayback`);
`PlaceholderVideoProvider` is the only implementation, honestly reporting
zero capability. This is a deliberate seam, not incomplete work — a
future `RTSPProvider`/`WebRTCProvider`/`HLSProvider` plugs in without
touching any consumer (`LiveCameraTile`, Calibration Center's video area,
etc.).

**What's missing:** the implementation itself, blocked on a real backend
video-delivery contract (`ADR-011` mandates "backend-controlled video
delivery," but no endpoint/URL scheme is defined yet —
`FRONTEND_ARCHITECTURE.md` §8).

**Trigger to fix:** a video-delivery contract exists on the backend side.
Not frontend-actionable before then.

---

## D-5. Telemetry/observability hooks are inert

**Where:** `src/api/client.ts`'s `ApiClientHooks`
(`onRequestStart`/`onRequestEnd`).

Built as extension points during Phase 1 specifically so a real metrics/
tracing/logging implementation could be wired in later without touching
`request()`'s call sites — currently no-ops. There is no request-level
latency tracking, error-rate monitoring, or distributed tracing anywhere
in the frontend today.

**What's missing:** an actual telemetry backend to send this data to
(e.g. OpenTelemetry, a metrics endpoint, structured log shipping) — none
exists in this air-gapped, single-node deployment today, so there's
currently nothing to wire the seam to.

**Trigger to fix:** a decision on what observability infrastructure (if
any) this deployment target needs, given it's air-gapped by design
(`CLAUDE.md`'s Offline First principle) — likely a local
logging/metrics story rather than a cloud APM, worth scoping
deliberately rather than defaulting to a typical SaaS observability stack.

---

## D-6. Performance thresholds with no current trigger

**Where:** Evidence Viewer, Threat Review Center, Calibration Center.

Recorded in full in `FRONTEND_ARCHITECTURE.md` §17; summarized here as
debt-with-a-tripwire rather than debt-to-fix-now:

| Area | Current approach | Threshold |
|---|---|---|
| Evidence Viewer | Fetches entire `GET /evidence` table, filters client-side | ~1,000 items |
| Evidence recording preview | Fetches whole file as a `Blob` before playback | ~200 MB per recording |
| Threat Review Center | Plain list, no virtualization | ~100 simultaneously visible rows |
| Calibration Center | Full historical log as one table | ~500 rows |

These are engineering-judgment estimates, not measurements — this
deployment has no real evidence/review volume yet. Revisit the numbers
once real volume exists rather than treating them as validated.

---

## D-7. No local i18n infrastructure

**Where:** N/A — deliberately not built.

The prototype's Settings screen had a language selector (English/Bengali)
with no actual translation behind it. RM-13 dropped it entirely rather
than keep a non-functional dropdown or build real i18n infrastructure
speculatively (`react-i18next` or equivalent, a translation-string
extraction workflow, at least one complete Bengali translation) with no
current requirement driving it.

**Trigger to build:** an explicit product requirement for multi-language
operator support. Not speculative work until then.

---

## D-8. Two files carry a co-located provider + hook (fast-refresh warning)

**Where:** `src/auth/AuthProvider.tsx`, `src/video/VideoProviderContext.tsx`.

Both export a React context provider component and its corresponding
`useX()` hook from the same file — the standard, idiomatic React context
pattern, but it trips `react-refresh/only-export-components` (Vite's Fast
Refresh works best when a file exports only components). Two warnings,
zero errors, present since Phase 1/Phase 2 respectively and left as-is
deliberately rather than split into two files each purely to silence a
dev-experience lint warning with no runtime effect.

**Trigger to fix:** none needed — cosmetic, dev-server-only impact
(occasionally loses component state on hot-reload of these two files).
Would only be worth revisiting if it starts causing real friction during
active development on either file.