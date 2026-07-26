# Frontend Context

---

# Frontend Repository

Name:
`frontend/` (this repository — Radar-Eye)

Former location:
`radar-eye-command` (https://github.com/CodeHub1443/radar-eye-command) — the original Lovable-generated prototype. Its full commit history was imported into this repository via `git subtree` on 2026-07-26 (Repository Consolidation initiative); it is no longer a separate development target. `frontend/docs/` carries the RM-13 migration's own detailed records (`FRONTEND_ARCHITECTURE_REVIEW.md`, `RM-13_MIGRATION_SUMMARY.md`, `BACKEND_CAPABILITY_GAPS.md`, `TECHNICAL_DEBT.md`).

Purpose:
Radar Eye Command Center User Interface

Status:
RM-13 complete — every screen consumes real backend data through a layered (DTO → mapper → domain model → view model → UI) pipeline; zero mock data remains.

Integration Status:
Integrated — merged into `develop` (2026-07-26), living at `frontend/` alongside `apps/`, `services/`, `shared/`.

Architecture Status:
Aligned with backend architecture (see Major Architectural Alignment Required / Health Monitoring Alignment below — both resolved).

---

# Technology Stack

Framework:
React 19

Language:
TypeScript

Build Tool:
Vite

Routing:
TanStack Router

Data Fetching:
TanStack Query

UI Framework:
TailwindCSS

Component Library:
Radix UI

Icons:
Lucide React

---

# Design Goal

Provide a real-time military command center interface for:

- Surveillance Operations
- Threat Monitoring
- Incident Management
- Tactical Visualization
- System Monitoring
- Evidence Review

---

# Current State

`frontend/src/lib/mock-data.ts` no longer exists — deleted once nothing referenced it (verified via repo-wide grep before deletion, per `frontend/docs/RM-13_MIGRATION_SUMMARY.md`).

Every screen (Live Monitoring, Tactical Map, Camera Management, Incident Center, Threat Review Center, Calibration Center, Evidence Viewer, AI Analytics, System Health, Settings) is real-data-driven, per `frontend/docs/UI_SCREEN_CATALOG.md`'s full 10-screen catalog.

---

# Integration Strategy

Completed: Mock Data → REST APIs + WebSocket Streams, per `frontend/docs/FRONTEND_ARCHITECTURE_REVIEW.md`'s five-layer pipeline (Transport DTO → Mapper → Domain Model → View Model → UI). All operational data originates from Radar Eye backend services (RM-12's API layer); WebSocket writes update the same TanStack Query cache REST populates, never a parallel store.

Not yet exercised: an actual integrated run of `apps/api` + `frontend/` against each other on `develop` (RM-13's own verification worked against RM-12's OpenAPI schema exported from its branch, not a running merged instance) — see Phase D of the Repository Consolidation plan / the Repository Integration Completion Report.

---

# Major Architectural Alignment Required — Resolved

Threat Model

Was:
- Alert Level 1 / 2 / 3

Now:
- ALLY / OBSERVE / LOW / MEDIUM / HIGH / HUMAN_REVIEW (`frontend/src/domain/threatLevel.ts`, the one place this mapping exists — every screen displaying a threat level goes through it)

---

# Health Monitoring Alignment — Resolved

System Health now shows only what `apps/api`'s `/health/*` endpoints actually provide: GPU (nullable, honestly empty outside NVML/Jetson hardware), storage, per-camera connection status, and a fixed 5-key component-status map. The prototype's generic CPU/memory/network/ambient-temperature panels — consistent with a discrete-workstation assumption, not the single-Jetson-SoC deployment target — were dropped rather than kept with fabricated numbers; recorded as a backend capability gap (not yet exposed by any endpoint) in `frontend/docs/BACKEND_CAPABILITY_GAPS.md` (G-11) if ever wanted.

---

# Frontend Ownership

Owner:
@frontend

Architecture Authority:
@architect

Backend Integration Authority:
@backend

Changes affecting architecture require review.