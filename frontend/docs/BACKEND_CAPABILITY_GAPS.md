# Backend Capability Gap Register

**Status:** Planning input for RM-14+. Every item below was found during
RM-13 by checking a real screen's requirements against the actual backend
schema/router source — none are speculative. Per the RM-13 review's
explicit instruction, this is an engineering backlog, not implementation
guidance: no item was worked around or simulated client-side; each was
either dropped, replaced with an honest reduced/alternate UI, or shown as
an explicit disabled state instead.

Complexity estimates are the frontend engineer's read of the backend
source consulted during RM-13 (`apps/api`, `services/`, `shared/schemas`)
— informed, not authoritative. Backend engineering should re-estimate
before committing any item to a milestone.

---

## Tier 1 — Highest impact

### G-1. No live or reference frame endpoint for camera calibration
- **Description:** No endpoint anywhere returns a still image or live
  frame for a camera. `POST /calibration/start` accepts reference points
  as raw `(image_x, image_y)` pixel coordinates with no way to see the
  image those coordinates are relative to.
- **Affected workflow:** Calibration Center. This is the single most
  impactful gap found in RM-13 — an operator cannot visually place
  calibration points and must know pixel coordinates by other means
  (e.g. reading them off a separate tool or a printed reference image).
- **Business impact:** High. Calibration accuracy depends on precise
  point placement; numeric-only entry is workable for an engineer but not
  a realistic field workflow for regular re-calibration.
- **Priority:** Tier 1.
- **Estimated backend complexity:** **Medium–High.** Requires either (a)
  a frame-capture mechanism in `apps/deepstream`'s pipeline (grab and
  serve one JPEG on demand) plus a new `apps/api` endpoint to trigger and
  retrieve it, or (b) reusing an existing snapshot if one is recent
  enough. Likely blocked on the same live-video-delivery architecture
  decision noted in `docs/FRONTEND_ARCHITECTURE.md` §8 (ADR-011) — worth
  scoping together rather than solving calibration's need in isolation.

### G-2. `HumanReviewSchema` has no `created_at`/timestamp field
- **Description:** Every other list-bearing schema (`IncidentSchema`,
  `CameraSchema`, `RecordingSchema`) has a timestamp. `HumanReviewSchema`
  does not.
- **Affected workflow:** Threat Review Center — the review queue cannot
  be sorted or aged chronologically; operators can't tell how long an
  item has been waiting.
- **Business impact:** High. CLAUDE.md's Human Review Rules require
  operator action on unknown uniforms; without an age signal, the queue
  can't be prioritized or SLA'd.
- **Priority:** Tier 1.
- **Estimated backend complexity:** **Low.** Add a `created_at` column to
  `human_review_items` (migration) and the corresponding schema field —
  same shape as every other entity's timestamp.

### G-3. No `GET /audit-log` (or equivalent) endpoint
- **Description:** The `audit_log` table exists (added during RM-12
  Phase 2, closing a real ADR-008/`DATABASE_SCHEMA.md` gap) and is
  actively written to by every audited mutation, but nothing reads it
  back over the API.
- **Affected workflow:** System Health's Event Log Stream panel, Settings'
  Audit Log tab — both shown as explicit disabled states.
- **Business impact:** High. Auditability is a stated CLAUDE.md core
  principle ("every incident must have... detection source, classification
  result..." / "all threat decisions must be explainable"); the data
  exists and is simply unreachable from the operator UI.
- **Priority:** Tier 1.
- **Estimated backend complexity:** **Low–Medium.** The table and write
  path already exist; this is a new read-only `GET /audit-log` endpoint
  with pagination (see G-11) and reasonable filtering (by actor, action,
  resource, date range).

### G-4. WebSocket message schemas have no generated-type coverage
- **Description:** FastAPI's OpenAPI output has no WebSocket
  representation at all — a structural limit of OpenAPI, not a gap in how
  the schema was exported. Every `/ws/*` message shape is hand-typed in
  `src/ws/messages.ts` against `shared/schemas/*.py`, with no compiler or
  generator to catch drift.
- **Affected workflow:** All five WS channels (threats, incidents,
  camera_health, reviews, alarms) — every consumer.
- **Business impact:** Medium–High. Not a current defect, but a silent
  backend field rename would only surface as a frontend runtime bug, not
  a build failure — real risk for a system where WS carries operationally
  important real-time state.
- **Priority:** Tier 1.
- **Estimated backend complexity:** **Medium.** Options already scoped in
  `FRONTEND_ARCHITECTURE.md` §13: a small export script that introspects
  the WS-message Pydantic classes (they're ordinary `BaseModel`
  subclasses, not FastAPI-route-bound) and emits JSON Schema per channel;
  or adopting AsyncAPI; or, at minimum, a backend-side contract test
  asserting each `websockets/bridge.py` translator's output still matches
  its schema's field set.

---

## Tier 2

### G-5. No server-side pagination/filtering on `GET /evidence`, `GET /recordings`, `GET /reviews`
- **Description:** All three always return the complete table. No
  `limit`/`offset`/`cursor` parameter, no filter query params (by
  incident, camera, type, status, date range).
- **Affected workflow:** Evidence Viewer, Threat Review Center.
- **Business impact:** Medium today, growing. Fine at current scale
  (single node, 20 cameras); becomes a real operator usability and
  client-performance problem as evidence/review volume accumulates over
  weeks/months of continuous recording. Concrete client-side thresholds
  are recorded in `TECHNICAL_DEBT.md`.
- **Priority:** Tier 2.
- **Estimated backend complexity:** **Low–Medium.** Standard limit/offset
  pagination plus a handful of filter params on existing, already-simple
  repository-backed list queries.

### G-6. No recording streaming or HTTP range-request support
- **Description:** `GET /recordings/{id}/download` returns the entire
  file in one `FileResponse`. No `Range` header support, no chunked
  delivery.
- **Affected workflow:** Evidence Viewer's inline recording preview
  currently fetches the whole file as a `Blob` before playback is
  possible.
- **Business impact:** Medium. Works today; will degrade for longer
  recordings (see `TECHNICAL_DEBT.md`'s ~200MB threshold) and blocks
  seek-without-full-download, a normal expectation for video review.
- **Priority:** Tier 2.
- **Estimated backend complexity:** **Medium–High.** FastAPI's
  `FileResponse` doesn't do range requests out of the box; needs a custom
  streaming response handling `Range`/`Accept-Ranges`/`Content-Range`
  headers and partial-read file I/O. Compounds with G-15 (H.265 browser
  support) — worth solving together if a transcode-on-demand path is ever
  built.

### G-7. No `/ws/reviews` resolution/status-change event
- **Description:** `/ws/reviews` carries `HumanReviewItemCreatedEvent`
  only. No event fires when a review item is resolved (confirmed,
  escalated, dismissed) by any operator.
- **Affected workflow:** Threat Review Center — a second operator's
  browser doesn't get a live push when someone else resolves an item;
  only the acting client's own REST response updates their view.
  Mitigated client-side with a short `staleTime` + refetch-on-focus, not
  solved.
- **Business impact:** Medium. Reviews are typically resolved quickly by
  whoever is looking at the queue; the staleness window is short in
  practice, but a genuinely simultaneous multi-operator queue would show
  stale state briefly.
- **Priority:** Tier 2.
- **Estimated backend complexity:** **Low–Medium.** Mirrors the pattern
  already built for incidents (`IncidentUpdatedSchema` +
  `websockets/bridge.py`'s translator/subscription wiring) — same shape
  of work, applied to reviews.

### G-8. `/analytics/*` are coarse aggregate counts only
- **Description:** `ThreatAnalyticsSchema`/`IncidentAnalyticsSchema`/
  `CameraAnalyticsSchema`/`SystemAnalyticsSchema` are simple repository-
  query aggregations by design (RM-12's own stated scope) — no
  time-windowed trends, no precision/recall/F1, no response-time
  percentiles, no per-sector heatmap, no weapon-frequency breakdown.
- **Affected workflow:** AI Analytics — the largest single reduction in
  visual density of the entire RM-13 migration.
- **Business impact:** Medium. Coarse totals are operationally useful;
  trend/performance analytics would meaningfully improve situational
  awareness and model-performance visibility over time.
- **Priority:** Tier 2.
- **Estimated backend complexity:** **High.** Time-windowed trends need
  either periodic snapshotting or timestamped event aggregation queries;
  precision/recall requires ground-truth labeling infrastructure that
  doesn't exist; a heatmap needs spatial data (see G-9) as a
  precondition. Likely several separate pieces of work, not one.

---

## Tier 3

### G-9. No camera geo-coordinates (lat/lng or any grid position)
- **Description:** `CameraSchema.location` is free text
  (`"North Gate · Sector A"`) — never a coordinate of any kind.
- **Affected workflow:** Tactical Map — rebuilt as a non-spatial status
  board grouped by the location string specifically because of this gap;
  a real positioned map cannot exist without it.
- **Business impact:** Medium. A textual status board is operationally
  usable; a real spatial view is the more natural interface for a
  perimeter-security console once camera positions are known.
- **Priority:** Tier 3 (not explicitly ranked at the RM-13 review; placed
  here on impact/complexity balance — revisit if Tactical Map's spatial
  view becomes a near-term priority).
- **Estimated backend complexity:** **Low–Medium** for the schema change
  itself (add `latitude`/`longitude` or a site-local x/y column +
  migration); the larger cost is operational — surveying and entering
  real camera positions — not backend code.

### G-10. Expanded camera configuration
- **Description:** `CameraUpdateRequestSchema` supports name/location/
  status only. No resolution, codec, confidence threshold, detection-
  class selection, privacy-mask zones, or firmware-version field exists
  anywhere on the backend.
- **Affected workflow:** Camera Management's configuration modal, reduced
  to the three real fields.
- **Business impact:** Low–Medium. These are meaningful operational
  controls, but likely belong to DeepStream pipeline configuration
  (per-camera stream profiles) rather than the `cameras` table — a
  different subsystem's scope, not a simple schema extension.
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Medium.** Depends heavily on
  whether these become per-camera DB-backed settings (straightforward) or
  require live pipeline reconfiguration (touches `apps/deepstream`,
  needs a config-reload or restart story).

### G-11. Advanced operational metrics (CPU, memory, network, ambient temperature)
- **Description:** `SystemHealthSchema` covers GPU, storage, cameras, and
  a fixed 5-key component-status map. No CPU/memory/network/ambient-
  temperature metric exists.
- **Affected workflow:** System Health, Live Monitoring — both dropped
  the prototype's corresponding panels outright.
- **Business impact:** Low. Reasonable operational nice-to-haves;
  consistent with the single-Jetson-SoC deployment target rather than a
  clear gap against a stated requirement.
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Low–Medium.** Same collector
  pattern already used for GPU/storage (`apps/api/app/health/collector.py`)
  — standard host-metrics collection (`psutil` or equivalent), no new
  architectural concept.

### G-12. No `GET /auth/me`
- **Description:** No endpoint returns the current user's own profile.
  Username isn't in the JWT payload either.
- **Affected workflow:** Auth foundation — username is carried from the
  login form input rather than fetched, and doesn't survive a scenario
  where the frontend needs to reconstruct identity without a fresh login
  (already handled via `tokenStore` persisting it alongside tokens, but
  that's a workaround for absence, not a real source).
- **Business impact:** Low. Works today; would simplify the auth layer
  and remove one frontend-side assumption (see `TECHNICAL_DEBT.md`).
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Low.** Trivial endpoint — decode
  the caller's own token, return their `UserSchema` row.

### G-13. Incident/IncidentSummary carry no weapon type, assigned operator, confidence score, escalation field, or location
- **Description:** None of these exist on `IncidentSchema`/
  `IncidentSummarySchema`. They're `ThreatAssessment`-level concepts
  (weapon type) or don't exist as a backend concept at all (assigned
  operator, escalation-at-the-incident-level, confidence score persisted
  post-detection).
- **Affected workflow:** Incident Center — the prototype's card/detail
  view assumed all four.
- **Business impact:** Low–Medium. An incident's associated
  `ThreatAssessment` data is available via the `threats` domain
  separately; "assigned operator" and "incident-level escalation" may be
  deliberate backend design choices (escalation is a `HumanReviewItem`
  action, not an `Incident` transition) rather than gaps to close.
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Low** per field if any are wanted
  (e.g. an `assigned_operator_id` column), but recommend product/backend
  confirm which of these are intentionally absent by design before
  treating this as a backlog item at all.

### G-14. No time-windowed incident aggregates
- **Description:** `IncidentAnalyticsSchema` is all-time totals and
  counts-by-status only — no "resolved in the last 24h," no average
  response time.
- **Affected workflow:** Incident Center, AI Analytics — the prototype's
  "Resolved 24h"/"Avg. Response" stats had no real replacement.
- **Business impact:** Low–Medium. Useful shift-level operational
  metrics; same underlying need as G-8's time-windowing gap.
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Medium.** Needs a windowed query
  (e.g. `WHERE resolved_at > now() - interval '24 hours'`) and a response-
  time computation from `incident_events` timestamps — doable without new
  infrastructure, but not a trivial aggregate.

### G-15. Evidence download responses don't expose filename/extension/content-type; recordings are H.265
- **Description:** Two related gaps. (a) Neither `EvidenceItemSchema`
  nor the download response exposes the original filename or MIME type —
  the frontend guesses a save-as filename. (b) Recordings are archived as
  H.265, and browser `<video>` playback support for H.265 is unreliable
  across browsers — inline preview in Evidence Viewer is best-effort;
  download (the unmodified original file) always works regardless.
- **Affected workflow:** Evidence Viewer.
- **Business impact:** Low. Download always works; this affects the
  polish of the in-browser preview experience only.
- **Priority:** Tier 3.
- **Estimated backend complexity:** **Low** for (a) — add a
  `Content-Disposition`/`Content-Type` header or a filename field to the
  schema. **High** for (b) if "fix browser playback" means transcode-on-
  demand or a browser-compatible mezzanine format — a real
  DeepStream/storage-pipeline decision, not a quick fix, and should be
  scoped together with G-6 (streaming) if pursued.

---

## Summary table

| ID | Gap | Tier | Backend complexity |
|---|---|---|---|
| G-1 | Live/reference frame endpoint for calibration | 1 | Medium–High |
| G-2 | `HumanReview` timestamps | 1 | Low |
| G-3 | `GET /audit-log` | 1 | Low–Medium |
| G-4 | WS schema generation / contract validation | 1 | Medium |
| G-5 | Evidence/recordings/reviews pagination & filtering | 2 | Low–Medium |
| G-6 | Recording streaming / range-request support | 2 | Medium–High |
| G-7 | `/ws/reviews` completion events | 2 | Low–Medium |
| G-8 | Richer analytics (trends, precision/recall, heatmap) | 2 | High |
| G-9 | Camera geo-coordinates | 3 | Low–Medium |
| G-10 | Expanded camera configuration | 3 | Medium |
| G-11 | Advanced operational metrics (CPU/mem/network) | 3 | Low–Medium |
| G-12 | `GET /auth/me` | 3 | Low |
| G-13 | Incident weapon/operator/confidence/escalation/location | 3 | Low (per field) |
| G-14 | Time-windowed incident aggregates | 3 | Medium |
| G-15 | Evidence filename/content-type + H.265 browser support | 3 | Low / High |