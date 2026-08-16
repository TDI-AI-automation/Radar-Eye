# Frontend Gap Analysis

**Status (2026-07-26):** RM-13 complete, merged into `develop` at `frontend/` via the Repository Consolidation initiative. Every gap below is resolved; entries are kept, not deleted, as the historical record of what RM-13 actually closed. See `frontend/docs/RM-13_MIGRATION_SUMMARY.md` for the full retrospective and `frontend/docs/BACKEND_CAPABILITY_GAPS.md` for what remains open on the *backend* side (never worked around client-side).

---

# Audit Summary

Frontend Repository:
`frontend/` (formerly the standalone `radar-eye-command` repository)

Assessment:

The frontend was substantially reusable, as predicted. The prototype's visual/interaction design was preserved; its data flow was replaced entirely.

Estimated Reuse:

70% - 80% (confirmed accurate in hindsight)

A complete rewrite was not required.

---

# Existing Strengths

The following areas align well with architecture:

- Live Monitoring
- Incident Center
- Tactical Map
- Camera Management
- Settings

These screens should be preserved and integrated.

---

# Mock Data Dependency — Resolved

`src/lib/mock-data.ts` no longer exists. Removed once zero screens referenced it (verified via repo-wide grep before deletion).

Replacement Strategy (implemented as planned):

TanStack Query
+
Backend APIs (RM-12)
+
WebSocket Streams

---

# Threat Model Mismatch — Resolved

Was:

- Alert Level 1 / 2 / 3

Now:

- ALLY / OBSERVE / LOW / MEDIUM / HIGH / HUMAN_REVIEW, one mapping (`frontend/src/domain/threatLevel.ts`) shared by every screen

Priority was High — closed.

---

# System Health Mismatch — Resolved

System Health now shows only real `apps/api` `/health/*` data (GPU, storage, per-camera status, component-status map) — no generic infrastructure metrics. The Jetson/DeepStream/TensorRT/PostgreSQL-specific framing was correct; the resolution was to show *less*, honestly, rather than fabricate deployment-specific numbers the backend doesn't provide (e.g. no CPU/memory/network endpoint exists — tracked as `frontend/docs/BACKEND_CAPABILITY_GAPS.md` G-11 if ever wanted, not built around).

Priority was Medium — closed.

---

# Capability — Built

Threat Review Center

Required By:

THREAT_ENGINE_SPEC.md

Status:

Built (`frontend/src/routes/reviews.tsx`) — keyboard-driven queue (J/K navigate, M/C/E/X arm the four resolution actions), per the RM-13 Phase 3 review's "highest-traffic operator screen" emphasis.

Priority was High — closed.

---

# Capability — Built

Calibration Center

Required By:

CAMERA_CALIBRATION_SPEC.md

Status:

Built (`frontend/src/routes/calibration.tsx`) — numeric reference-point entry (no live/reference-frame endpoint exists on the backend, tracked as `frontend/docs/BACKEND_CAPABILITY_GAPS.md` G-1, Tier 1), real calibration history log, real Validate tool.

Priority was High — closed.

---

# Capability — Built

Evidence Viewer

Required By:

RECORDING_POLICY.md

Status:

Built (`frontend/src/routes/evidence.tsx`) — read-only by design (zero mutation routes exist on the backend for evidence, matching CLAUDE.md's Evidence Preservation principle); inline preview + download only.

Priority was Medium — closed.

---

# Integration Readiness

Frontend Structure:
Ready

Frontend Routing:
Ready

Frontend Component System:
Ready

Backend Integration:
Built (all 10 `UI_SCREEN_CATALOG.md` screens on the DTO → mapper → domain model → view model → UI pipeline) — not yet exercised against a live merged `apps/api` + `frontend/` run on `develop` in the same process; RM-13's own verification worked against RM-12's OpenAPI schema exported from its branch. See the Repository Integration Completion Report's Phase D for the remaining live-integration verification step.

Real-Time Event Integration:
Built — WebSocket writes go into the same TanStack Query cache REST populates (invalidate-over-merge, applied uniformly); same live-integration caveat as above applies.

Overall Assessment:

Frontend architecture reached production evolution as planned. Remaining work is backend capability expansion (`frontend/docs/BACKEND_CAPABILITY_GAPS.md`), not frontend architecture.