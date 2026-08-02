# RM-13 Migration Summary

**Status:** RM-13 complete, closed. This is the retrospective record of
what changed and why. For current-state architecture, see
`FRONTEND_ARCHITECTURE_REVIEW.md`. For the phase-by-phase journal this was
drawn from, see `FRONTEND_ARCHITECTURE.md`.

**Scope:** transform the Lovable-generated visual prototype
(`radar-eye-command`) into the production Radar Eye Command frontend,
consuming the real RM-12 backend. The prototype's UX/interaction design
was preserved as a reference; its internal data flow, mock data, and any
assumption unbacked by the real backend was not.

---

## 1. Prototype capabilities removed

Removed rather than kept with fabricated data, once the real backend
surface was checked against each screen:

- **Camera configuration**: resolution, codec, confidence threshold,
  detection-class toggles, privacy-mask zones, firmware version. Only
  name/location/status are real, editable fields
  (`CameraUpdateRequestSchema`).
- **AI Analytics**: 24-hour hourly trend chart, precision/recall/F1/
  false-positive/false-negative metrics, response-time percentiles, a
  per-sector threat heatmap, weapon-frequency breakdown. RM-12's
  `/analytics/*` endpoints are coarse aggregate counts only — the largest
  single reduction in visual density of the entire migration.
- **System Health**: CPU, memory, ambient temperature, network uplink,
  MQTT broker, notification bus panels — no endpoint exists for any of
  them. Event Log Stream (no `GET /audit-log`).
- **Incident Center**: weapon type/object, assigned operator, confidence
  score, escalation field, free-text location, "resolved in 24h"/average
  response-time stats, Assign and Export actions, the fabricated
  response-timeline steps (replaced with the real event log).
- **Live Monitoring**: the bounding-box detection overlay (no pixel-space
  coordinates exist anywhere in the backend) and the autoplay demo video
  (no live video delivery mechanism exists) — both flagged as an "open
  backend dependency" as early as Phase 0, acted on in the final phase.
  System Load panel (CPU/memory/network) and the Radar Sweep panel
  (fabricated blip positions) — same root causes as System Health and
  Tactical Map respectively.
- **Tactical Map**: the entire coordinate-driven map — camera x/y
  positions, rotation/field-of-view cones, patrol routes, blind-spot
  polygons, restricted-zone overlays. `CameraSchema.location` is free
  text; no coordinate field of any kind exists on the backend.
- **Settings**: AI Model tab (confidence threshold, detection classes,
  tracking-model selector, escalation-rule text) and Notifications tab —
  both explicitly deferred backend capabilities
  (`docs/OPEN_QUESTIONS.md` Q-014). Audit Log tab (no endpoint). The
  entire System tab (language selector with no i18n infrastructure
  anywhere in the app, an unwired animation toggle, a fabricated backup
  schedule, a fabricated version/build string) — dropped outright, not
  disabled, since none of it connected to anything real or was worth
  building in isolation.
- **Evidence** (new screen, not a removal but a constraint): no edit,
  rename, delete, or annotate affordance was ever built — the backend
  exposes zero mutation routes for evidence, and the UI mirrors that
  exactly.

## 2. Backend-driven UI changes

Where the backend's real shape was richer, leaner, or simply different
from the prototype's assumption, the UI followed the backend:

- **Threat model**: the prototype's fabricated 1/2/3 severity scale
  replaced everywhere with the backend's real six-value `ThreatLevel`
  (`ALLY/OBSERVE/LOW/MEDIUM/HIGH/HUMAN_REVIEW`).
- **Camera Management**: table columns reduced to what
  `CameraSchema`/`CameraHealthSchema` actually provide (status, fps,
  last-frame-age), joined client-side from two endpoints.
- **Incident list vs. detail**: `GET /incidents` returns a leaner
  `IncidentSummarySchema` than `GET /incidents/{id}}`'s full
  `IncidentSchema` — Phase 0's domain model didn't anticipate this,
  triggering the `IncidentSummary` refinement (§3).
- **Tactical Map**: rebuilt as an honest, non-spatial operational status
  board grouped by the real `location` string, with a visible banner
  explaining the gap, per the explicit "no synthetic map intelligence"
  instruction.
- **Settings**: reorganized into Administrative (real, backend-backed:
  Roles & Users), Fixed Policy (real but not editable: Recording Policy,
  trimmed to exactly what `CLAUDE.md` states), and Unavailable (explicit
  disabled panels, not silent removal).
- **Calibration Center**: built around the one real constraint that
  shaped it — no endpoint exists to retrieve a live or reference camera
  frame, so reference-point entry is numeric, not point-and-click.
  Calibration history is the real, full historical log (append-only),
  giving the screen the "engineering workstation" character requested
  rather than an administrative settings page.
- **Threat Review Center**: built for keyboard efficiency (J/K navigate,
  M/C/E/X arm the four resolution actions, second press confirms) as the
  highest-traffic operator screen, with the one fact
  (`HumanReviewItem.canResolve()`) backing all four actions since the
  backend's `_resolve()` rejects any of them identically once an item
  leaves `OPEN`.

## 3. Architectural decisions

The full record lives in `FRONTEND_ARCHITECTURE.md`; the ones with
lasting structural impact:

- **OpenAPI-generated types as the read-only transport source of truth**,
  regenerated from the backend's live schema, never hand-patched.
- **A five-layer pipeline** (DTO → mapper → domain model → view model →
  UI) applied with zero exceptions across every screen, including the two
  screens (Analytics, Health) where the domain-model layer is
  legitimately a pass-through rather than skipped.
- **`localStorage` for token storage**, approved with an explicit
  rationale (frozen RM-12 backend contract, air-gapped/single-tenant
  threat model, multi-tab ops-room usability), accepting the SSR/
  client-side-only-enforcement tradeoff it implies.
- **WebSocket writes only into the TanStack Query cache** (never a
  parallel store), and **invalidate over merge**, applied uniformly even
  where a merge would have been technically safe.
- **A capability-flagged `VideoProvider` seam**, built once in Phase 0,
  reused without modification through every later phase including the
  final one.
- **Domain facts vs. authorization**: resolved once
  (`usePermission()` owns all "can this user" decisions; domain models
  never get a `hasRole()`-shaped method), then applied consistently
  rather than re-litigated per screen.
- **Query-hook placement by consumer count**: cross-feature data lives in
  `queries/`, single-feature data lives in `features/*/hooks/` — actively
  enforced by relocating `useCameras`/`useCamerasHealth` once a second
  consumer appeared, rather than left in its original, now-inconsistent
  location.

## 4. Lessons learned

- **Reading the OpenAPI schema first, before writing any screen code,
  caught every major scope surprise before implementation time was spent
  on it** — Analytics' real aggregate-only shape, the missing calibration
  reference-image endpoint, and the Incident list/detail DTO split were
  all found during investigation, not discovered mid-build.
- **The Incident list/detail split was the one real domain-model gap
  Phase 0 didn't anticipate.** The fix (extracting `incidentStatus.ts`/
  `threatLevel.ts` into pure-function modules shared by both `Incident`
  and the new `IncidentSummary`) generalizes: any future domain with a
  summary/detail DTO split should default to this pattern rather than
  fabricating placeholder fields to satisfy one class's constructor.
- **"No mock data" has a real cost that has to be spent deliberately, not
  minimized.** Analytics in particular went from the visually richest
  screen in the prototype to the plainest in the production build. That
  tradeoff was made explicitly and documented, not smoothed over — the
  alternative (fabricated-but-pretty charts) would have been strictly
  worse for an operational surveillance tool.
- **A missing backend capability is not always a blocker** — it's a
  design constraint to build honestly around (Calibration Center's
  numeric entry, Tactical Map's non-spatial board, Evidence's best-effort
  H.265 preview) or an explicit disabled state (Settings' three deferred
  tabs), and either response is preferable to a client-side workaround
  that would misrepresent system capability to an operator.
- **Consistency was worth enforcing even at a small performance cost** —
  the threats-channel WS merge that was technically safe but skipped to
  keep the invalidate-only rule uniform is the clearest example; it kept
  every screen's WS-handling code predictable to read without a special
  case to remember.

## 5. Production readiness assessment

The frontend is production-ready **for the capabilities the backend
currently exposes**. Concretely:
- Every screen consumes real data through a verified, layered pipeline;
  zero mock data remains anywhere in the application.
- Authentication and authorization are enforced consistently
  (`RouteGuard` + `usePermission()` + domain facts).
- Generated types are verified current against a live backend re-export
  (byte-identical diff at RM-13 close).
- `tsc --noEmit` and repo-wide `eslint` are both clean (0 errors).

What is **not** production-ready is a small, fully enumerated set of
backend capabilities the frontend cannot fabricate its way around —
tracked exhaustively in `BACKEND_CAPABILITY_GAPS.md`, prioritized for
RM-14+. None of these are frontend architectural deficiencies; each is a
missing endpoint, field, or event on the backend side. Separately, a small
set of frontend-side technical debt (retry-queue-on-401, WS schema
generation, performance thresholds with no current trigger) is tracked in
`TECHNICAL_DEBT.md` and does not block production use at current scale
(single node, 20 cameras).