# TASKS.md — Radar Eye Task Backlog

> **Authority:** This document is an Orchestrator artifact. Per `AGENTS.md`, the Orchestrator maintains the task backlog, creates implementation tickets, and assigns ownership. Only the Human (Tanvir) may approve scope changes (`RE-001`) and modify `AGENTS.md` / `CLAUDE.md`.
>
> **Rule enforced by this file:** *Every change must originate from a task. No code may be written without a task.* If work is needed and no task exists, the Orchestrator creates one here first.

- **Project:** Radar Eye — Military AI Surveillance Platform
- **Frontend repo:** https://github.com/CodeHub1443/radar-eye-command
- **Backend repo:** ⚠️ not created — see `RE-005`
- **Delivery deadline:** **2026-07-26**
- **Date of last update:** 2026-07-16
- **Days remaining:** 10

---

## 1. Sprint Reality Check

This section is factual, not editorial. It exists so the Human can make `RE-001` with real numbers.

### 1.1 Budget vs. capacity

| Phase | Scope | Estimate | Source |
|---|---|---|---|
| Phase 1 — AI | Model optimization + selection (remaining) | 1 day | Existing plan |
| Phase 2 — Software | Frontend UI | 2 days | Existing plan |
| Phase 2 — Software | Backend & API | 3 days | Existing plan |
| Phase 2 — Software | AI model integration + logic + scoring | 3 days | Existing plan |
| Phase 2 — Software | Deploy on Jetson | 1 day | Existing plan |
| Phase 3 — IoT | Flashlight + warning alarm | **no estimate** | Existing plan |
| Phase 4 — Evaluation | QA, bug, logic eval, RTSP frame drop | **no estimate** | Existing plan |
| | **Total estimated** | **10 days** | |
| | **Calendar available** | **10 days** | |

**The plan closes at exactly 100% utilization, with two phases carrying no estimate at all, and zero slack.** It only lands if all three of the following hold:

1. Frontend and Backend run **in parallel** under different owners (serial = 12+ days, misses).
2. Alarm hardware is **physically in hand today** (`PROJECT_CONTEXT.md` says "Hardware not finalized").
3. The Jetson performance budget works **on the first attempt** (never validated — see `RE-003`).

If any one fails, the date slips. `RE-001` exists to decide what gets cut *before* that happens, not after.

### 1.2 Documented scope vs. deliverable scope

`CLAUDE.md` and `PROJECT_CONTEXT.md` describe a system considerably larger than a 10-day build: 20 cameras across 2 Jetsons, DeepStream 7.0 + YOLO primary + ViT secondary, MQTT, JWT + RBAC, 30-day retention, and 7 future analytics modules. Nothing in those documents is marked as out-of-scope for 2026-07-26. **The docs are a product vision; this backlog is a delivery plan.** `RE-001` reconciles them.

### 1.3 Open blockers

| ID | Blocker | Blocks | Owner |
|---|---|---|---|
| `RE-001` | v1 scope for 2026-07-26 not agreed | Everything | `@tanvir` |
| `RE-002` | Alarm hardware not selected/procured | All of Phase 3 | `@tanvir` |
| `RE-003` | Jetson compute budget never measured | `RE-401`, `RE-203` | `@agent-vision` |
| `RE-004` | Node topology undefined (see 1.4) | `RE-201`, `RE-202` | `@orchestrator` |
| `RE-006` | Version triple is internally inconsistent | `RE-501` | `@agent-platform` |
| `RE-007` | 30-day retention is not physically possible as written | `RE-204` | `@tanvir` |

### 1.4 Architecture gaps found in the current documents

These are stated so they can be closed, not to relitigate decisions already made.

**a) `threatDetection-architecture.md` is an unmodified template.** Every field is still a placeholder (`[e.g., React, Next.js]`, `[Insert Project Name]`). It carries zero project information today. → `RE-008`

**b) Node topology is undefined.** `PROJECT_CONTEXT.md` assigns cameras 1–10 to Jetson A and 11–20 to Jetson B, but `CLAUDE.md` specifies **SQLite WAL**, which is a single-node, single-writer store. Unanswered: Does each Jetson own a local DB? Where does the frontend read from? Where does the Mosquitto broker run? Is there a third aggregator node? A two-node deployment with a single-node database is not yet a coherent design. → `RE-004`

**c) The version triple cannot all be true simultaneously.** `PROJECT_CONTEXT.md` specifies DeepStream 7.0 + JetPack 6.2 + CUDA 12.2. Per NVIDIA's support matrix, <cite index="10-1">DeepStream 7.0 targets JetPack 6.0 and CUDA 12.2, while DeepStream 7.1 targets JetPack 6.2/6.2.1/6.1 and CUDA 12.6</cite>. <cite index="6-1">JetPack 6.0 ships CUDA 12.2.1 and TensorRT 8.6.2</cite>. So the valid combinations are **DS 7.0 + JP 6.0 + CUDA 12.2** or **DS 7.1 + JP 6.2 + CUDA 12.6** — not the documented mix. Since `CLAUDE.md` makes DeepStream mandatory and Jetson deploy is budgeted at 1 day, discovering this during deploy week is expensive. → `RE-006`

**d) 30-day retention is off by roughly an order of magnitude.** 20 cameras × 4MP H.264 @ 30 FPS at a typical ~6 Mbps ≈ 120 Mbps aggregate ≈ **~1.3 TB/day ≈ ~39 TB per 30 days**. An AGX Orin Dev Kit has a single M.2 Key-M NVMe slot. Continuous 30-day video retention is not achievable on this hardware without external storage or an NVR. Retention almost certainly means *events + short clips + metadata*, but the document does not say so. → `RE-007`

**e) `AGENTS.md` defines the task schema but never names the agent roster.** It repeatedly constrains "Specialized Agents" without listing them, so `Owner` has no legal value set. Section 2.2 proposes one, pending `RE-009`.

**f) Inference stream not specified.** Running YOLO + ViT on 10 × 4MP main streams is the most expensive possible choice. Dahua/Hikvision cameras expose a sub-stream (typically D1/720p) — inference on sub-stream, recording on main stream, is the standard pattern and materially changes `RE-003`. Not mentioned anywhere. → `RE-402`

**g) No failover.** If Jetson A dies, cameras 1–10 go blind with no defined detection or notification path. → `RE-703` (degraded-mode alerting only; true HA is deferred).

---

## 2. Conventions

### 2.1 Task schema (mandated by `AGENTS.md`)

Every task **must** carry: `Owner`, `Description`, `Acceptance Criteria`, `Dependencies`. `Status`, `Priority`, and `Due` are Orchestrator additions for backlog management and do not replace the mandated four.

```
#### RE-XXX — Title
- **Owner:** @handle
- **Status:** Todo | In Progress | Blocked | In Review | Done
- **Priority:** P0 (must ship 07-26) | P1 (should) | P2 (deferred)
- **Due:** YYYY-MM-DD
- **Description:** What and why.
- **Acceptance Criteria:**
  - [ ] Measurable, verifiable outcome
- **Dependencies:** RE-XXX, RE-YYY | None
```

### 2.2 Owner roster — **PROPOSED, pending `RE-009`**

`AGENTS.md` does not define these. Do not treat as ratified.

| Handle | Role | Mandate |
|---|---|---|
| `@tanvir` | Human | Final authority. Scope, procurement, acceptance sign-off. |
| `@orchestrator` | Orchestrator | Architecture, ADRs, backlog, review. **May not write production code.** |
| `@agent-vision` | Specialized | DeepStream, TensorRT, YOLO/ViT, inference pipeline |
| `@agent-backend` | Specialized | FastAPI, SQLite, MQTT, APIs |
| `@agent-frontend` | Specialized | TypeScript UI |
| `@agent-platform` | Specialized | Jetson, JetPack, systemd, packaging, network |
| `@agent-iot` | Specialized | Relay/GPIO, siren, beacon |
| `@agent-qa` | Specialized | Test, evaluation, acceptance |

### 2.3 ID ranges

| Range | Area |
|---|---|
| `RE-0xx` | Blockers & decisions |
| `RE-1xx` | Phase 1 — AI |
| `RE-2xx` | Phase 2 — Backend & API |
| `RE-3xx` | Phase 2 — Frontend |
| `RE-4xx` | Phase 2 — AI integration & scoring |
| `RE-5xx` | Phase 2 — Jetson deployment |
| `RE-6xx` | Phase 3 — IoT device |
| `RE-7xx` | Phase 4 — Evaluation |
| `RE-9xx` | Deferred backlog |

### 2.4 Branch convention (per `CLAUDE.md`)

No direct commits to `main`. Branch name **must** carry the task ID: `feat/RE-203-mqtt-event-contract`, `fix/RE-701-rtsp-frame-drop`.

---

## 3. Blockers & Decisions — `RE-0xx`

#### RE-001 — Ratify v1 delivery scope for 2026-07-26
- **Owner:** `@tanvir`
- **Status:** Blocked (awaiting decision)
- **Priority:** P0
- **Due:** **2026-07-16 (today)**
- **Description:** Per `AGENTS.md`, no Specialized Agent may modify project scope and the Human is final authority. The documented system exceeds the 10-day budget (§1.1, §1.2). Decide explicitly what ships on 07-26 and what defers. Candidate de-scopes, each with its saving:
  - **Drop ViT secondary classifier for v1** (~1.5–2 days + removes the largest inference cost). Derive Military/Civilian from a rule over YOLO classes (e.g. person + rifle/RPG/pistol ⇒ Military) and keep ViT for v2.
  - **Deliver on 1 Jetson / 10 cameras**, scale to 2 nodes after acceptance (~1 day + kills the `RE-004` topology problem for v1).
  - **Retention = events + clips + metadata only**, no continuous recording (see §1.4d).
  - **Single admin login instead of full RBAC** (~1 day).
  - **Drop MQTT for v1**, use in-process events (~0.5 day). *Low saving — Mosquitto is cheap. Recommend keeping.*
- **Acceptance Criteria:**
  - [ ] A written "v1 Scope — 07-26" section is appended to `PROJECT_CONTEXT.md` listing IN and OUT items
  - [ ] Every P0 task in this file is traceable to an IN item; anything else is re-tagged P2
  - [ ] Decision is dated and signed by `@tanvir`
- **Dependencies:** None — **this blocks every other task**

#### RE-002 — Select and procure alarm hardware
- **Owner:** `@tanvir`
- **Status:** Blocked
- **Priority:** P0
- **Due:** **2026-07-16 (today)**
- **Description:** `PROJECT_CONTEXT.md` lists candidates (industrial relay controller, GPIO relay board, siren, beacon light) with status "Hardware not finalized". Phase 3 has no estimate and cannot start without a physical device. Procurement lead time is not zero. If the hardware is not already in hand, Phase 3 does not ship on 07-26 and must be de-scoped under `RE-001`.
- **Acceptance Criteria:**
  - [ ] Specific part selected, with interface documented (GPIO / USB-relay / Modbus RTU / RS-485)
  - [ ] Device physically present on the bench, powered, and confirmed switching a load
  - [ ] Voltage/current rating confirmed against the actual siren and beacon
  - [ ] If not in hand by EOD 07-16, `RE-001` moves Phase 3 to P2 and a GPIO stub ships instead (`RE-604`)
- **Dependencies:** None

#### RE-003 — Compute budget spike: measure the pipeline on real hardware
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P0 — **highest technical risk in the project**
- **Due:** 2026-07-18
- **Description:** No document states measured throughput. The target is 10 × 4MP @ 30 FPS with YOLO primary + ViT secondary on one AGX Orin 32GB, and the whole plan assumes it fits. It is currently an assumption. Measure it now, while there is still time to react; discovering a shortfall during "Deploy on Jetson" (day 9) leaves no room to fix it. Sweep the `interval` property on `nvinfer` (inference frame skipping) and sub-stream vs. main-stream.
- **Acceptance Criteria:**
  - [ ] `tegrastats` log captured over a ≥30 min run at target load, attached to this task
  - [ ] Reported: sustained aggregate FPS, per-stream FPS, GPU util, NVDEC util, RAM, power mode (MAXN vs. 30W), thermal throttle events
  - [ ] Result table for the matrix: {main-stream, sub-stream} × {YOLO only, YOLO+ViT} × {interval=0, 2, 4}
  - [ ] Explicit verdict written: **10 cams @ 30 FPS on one Orin — FITS / DOES NOT FIT**
  - [ ] If it does not fit, a mitigation recommendation is filed to `RE-001` (reduce FPS / raise `interval` / sub-stream inference / drop ViT / reduce cameras per node)
- **Dependencies:** `RE-101` (an optimized engine to benchmark)

#### RE-004 — ADR-001: Node topology and data ownership
- **Owner:** `@orchestrator`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** Resolve §1.4b. SQLite WAL is single-node/single-writer, but the deployment is two Jetsons. Decide and record: DB per node vs. central; broker location; what the frontend connects to; whether a third node exists. If `RE-001` selects single-Jetson v1, this ADR records that and defers the multi-node design to `RE-901`.
- **Acceptance Criteria:**
  - [ ] `docs/adr/ADR-001-node-topology.md` committed (per `CLAUDE.md`: architecture decisions require an ADR)
  - [ ] Contains a component diagram showing every node, DB, broker, and the frontend's read path
  - [ ] States where Mosquitto runs and how Jetson B's events reach the UI
  - [ ] Alternatives considered and rejected are recorded with reasons
- **Dependencies:** `RE-001`

#### RE-005 — Create backend repository and branch protection
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** Only the frontend repo is recorded. There is no backend repo, so `CLAUDE.md`'s "no direct commits to main / use feature branches" is currently unenforceable for backend work.
- **Acceptance Criteria:**
  - [ ] `radar-eye-backend` created, private
  - [ ] `main` protected; direct pushes blocked; PR required
  - [ ] `docs/adr/` directory seeded with an ADR template
  - [ ] Repo URL added to `PROJECT_CONTEXT.md`
- **Dependencies:** None

#### RE-006 — Resolve and pin the DeepStream / JetPack / CUDA triple
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** Fix §1.4c. Determine what the Jetsons are actually flashed with today, pick a valid combination, and pin it. Note that JP 6.0 → TensorRT 8.x and JP 6.2 → TensorRT 10.x; the TRT major version affects `RE-101` engine export, so this decision must land *before* optimization work.
- **Acceptance Criteria:**
  - [ ] Actual on-device versions captured from both units (`cat /etc/nv_tegra_release`, `deepstream-app --version`, `nvcc --version`, `dpkg -l | grep tensorrt`)
  - [ ] One valid triple selected and written into `PROJECT_CONTEXT.md` and `CLAUDE.md`, replacing the current inconsistent values
  - [ ] Verified against NVIDIA's official support matrix, link cited in the task
  - [ ] Reflash need assessed and, if required, scheduled — noting there is **no in-place upgrade between major JetPack versions**
- **Dependencies:** None

#### RE-007 — Define what "30-day retention" actually means
- **Owner:** `@tanvir`
- **Status:** Blocked
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** Resolve §1.4d. ~39 TB of continuous video does not fit on Jetson-attached NVMe. Decide: (a) events + clips + metadata only, (b) continuous recording onto an external NAS/NVR, or (c) reduced retention window. This determines the storage schema, the disk budget, and whether an NVR enters the architecture.
- **Acceptance Criteria:**
  - [ ] Retention policy stated per data class: event metadata / event clips / continuous video / model artifacts
  - [ ] Storage math recorded showing the chosen policy fits the actual disk
  - [ ] Physical disk capacity of both Jetsons confirmed and recorded
  - [ ] `PROJECT_CONTEXT.md` "Data Retention" section updated to be unambiguous
- **Dependencies:** `RE-001`

#### RE-008 — Populate `threatDetection-architecture.md`
- **Owner:** `@orchestrator`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-19
- **Description:** The file is an unmodified template (§1.4a). Fill it from `CLAUDE.md`, `PROJECT_CONTEXT.md`, and ADR-001. This is Orchestrator work ("Maintain architecture") and does not involve production code.
- **Acceptance Criteria:**
  - [ ] Zero `[placeholder]` strings remain in the file
  - [ ] §1 reflects the real directory tree of both repos
  - [ ] §2 diagram matches ADR-001
  - [ ] §10 Project Identification and §11 Glossary completed (define: GIE, PGIE, SGIE, RTSP, WAL, ADR, ViT, TRT)
  - [ ] Renamed to `ARCHITECTURE.md` for consistency with its own §1 reference
- **Dependencies:** `RE-004`

#### RE-009 — Ratify the agent roster in `AGENTS.md`
- **Owner:** `@tanvir`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-17
- **Description:** `AGENTS.md` mandates an `Owner` on every task but never enumerates the Specialized Agents, so `Owner` has no defined value set. Ratify §2.2 or replace it. Only the Human may modify `AGENTS.md`.
- **Acceptance Criteria:**
  - [ ] `AGENTS.md` gains a "Specialized Agents" section listing each handle and its mandate
  - [ ] Every `Owner` in this file resolves to a listed handle
- **Dependencies:** None

---

## 4. Phase 1 — AI — `RE-1xx`

> Data collection, preprocessing, annotation, training, and evaluation are **complete** (~2.5 months). Only optimization + selection remain.

#### RE-101 — Model optimization and final selection
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** The last open Phase 1 item (estimated 1 day). Export the trained YOLO to ONNX → TensorRT engine and select the final variant on the measured speed/accuracy trade-off. `CLAUDE.md` makes TensorRT deployment mandatory. Build the engine **on the target device** — TensorRT engines are not portable across TRT versions or GPU architectures.
- **Acceptance Criteria:**
  - [ ] ONNX export reproducible via a committed script
  - [ ] TRT engines built for FP16 and INT8 on the actual AGX Orin
  - [ ] INT8 calibrated on ≥1000 representative frames **from the deployment cameras**, not COCO
  - [ ] Comparison table committed: FP32 / FP16 / INT8 × {mAP@0.5, mAP@0.5:0.95, per-class AP, ms/frame}
  - [ ] Per-class recall reported separately for Rifle, RPG, Pistol, Fire — aggregate mAP hides the classes that matter
  - [ ] Final variant selected with the trade-off reasoning written down
  - [ ] Engine + calibration table archived with a version tag
- **Dependencies:** `RE-006`

#### RE-102 — ViT secondary classifier: TRT export and gate
- **Owner:** `@agent-vision`
- **Status:** Blocked
- **Priority:** P1 *(→ P2 if `RE-001` de-scopes ViT)*
- **Due:** 2026-07-19
- **Description:** Export the Military/Civilian ViT as a DeepStream SGIE (`nvinfer` secondary, `process-mode=2`) operating on PGIE person crops. This is the most expensive component in the pipeline; `RE-003` determines whether it is affordable at all.
- **Acceptance Criteria:**
  - [ ] TRT engine built and running as SGIE against PGIE person detections
  - [ ] Confusion matrix on held-out data, with **civilian→military false-positive rate reported explicitly**
  - [ ] Added latency measured in ms per detection at realistic detections-per-frame
  - [ ] `operate-on-class-ids` restricted to person only, verified
  - [ ] Ship/cut recommendation filed to `RE-001` based on `RE-003` headroom
- **Dependencies:** `RE-003`, `RE-001`

#### RE-103 — Freeze class list and label mapping
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-17
- **Description:** Lock the contract between model output and everything downstream. Class IDs leak into the DeepStream config, the DB schema, MQTT payloads, the scoring rules, and the UI. An index mismatch here is a silent, hard-to-find bug across four components.
- **Acceptance Criteria:**
  - [ ] `labels.txt` committed with frozen ordering: Person, Rifle, RPG, Pistol, Fire
  - [ ] `num-detected-classes` in the nvinfer config matches the label file
  - [ ] A single shared constant file is the source of truth for backend and frontend
  - [ ] Military/Civilian encoding defined (secondary class vs. attribute on Person)
- **Dependencies:** None

---

## 5. Phase 2 — Backend & API — `RE-2xx`

#### RE-201 — FastAPI service skeleton
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-19
- **Description:** Stand up the FastAPI app: config loading, structured logging, health endpoint, error handling, OpenAPI docs. Offline-first — no CDN fonts, no external calls, no telemetry, no license checks. The device is air-gapped; anything that phones home will hang on a timeout in the field.
- **Acceptance Criteria:**
  - [ ] `GET /health` returns service, DB, and broker status
  - [ ] Runs with the network cable physically unplugged, no errors, no hangs
  - [ ] All dependencies vendored/pinned and installable offline from a local wheelhouse
  - [ ] OpenAPI served locally at `/docs`
- **Dependencies:** `RE-005`, `RE-004`

#### RE-202 — SQLite WAL schema and migrations
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-19
- **Description:** Schema for cameras, events, detections, alarms, users, audit log. WAL mode with concurrent readers and a single writer. Note that under `RE-007` the write rate could reach thousands of detection rows per minute across 10 cameras — event-level rows, not per-frame rows.
- **Acceptance Criteria:**
  - [ ] `PRAGMA journal_mode=WAL` verified at runtime, not just configured
  - [ ] Migration tool committed; schema is versioned, not hand-edited
  - [ ] Indices on `(camera_id, timestamp)` and `(threat_class, timestamp)`
  - [ ] Write throughput measured at ≥10× expected peak event rate
  - [ ] Retention/purge job implemented per `RE-007` policy, with a dry-run mode
  - [ ] `busy_timeout` set; concurrent read-during-write proven not to raise `SQLITE_BUSY`
- **Dependencies:** `RE-007`, `RE-103`

#### RE-203 — MQTT event contract (Mosquitto)
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-20
- **Description:** Define the topic tree and payload schema carrying detections from the DeepStream pipeline to the backend and alarm subsystem. This is the seam between `@agent-vision` and `@agent-backend` — freeze it early so both can build against it in parallel.
- **Acceptance Criteria:**
  - [ ] Topic tree documented: `radareye/{node}/{camera_id}/detection`, `.../alarm`, `.../health`
  - [ ] JSON payload schema committed and versioned (`schema_version` field present from day one)
  - [ ] QoS per topic justified — detections vs. alarm commands have different delivery requirements
  - [ ] Mosquitto configured local-bind only, anonymous access disabled
  - [ ] Retained messages used for health/status, not for detections
  - [ ] Broker survives restart without losing alarm state
- **Dependencies:** `RE-103`, `RE-004`

#### RE-204 — Event + clip storage service
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-20
- **Description:** Persist events with a snapshot and a short clip around each threat detection. Disk is the hard constraint (§1.4d) — enforce a disk quota with oldest-first eviction, and never let the partition fill. A full disk on an air-gapped box in the field is an unrecoverable outage.
- **Acceptance Criteria:**
  - [ ] Snapshot + N-second pre/post clip written per event
  - [ ] Hard disk quota enforced; oldest-first eviction verified by test
  - [ ] Disk-full condition raises a health alert **before** it stops ingest
  - [ ] Storage path configurable; defaults to NVMe not eMMC
- **Dependencies:** `RE-202`, `RE-007`

#### RE-205 — Auth: JWT + RBAC
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P1 *(→ P2 if `RE-001` selects single-admin v1)*
- **Due:** 2026-07-21
- **Description:** `CLAUDE.md` specifies JWT + RBAC; `PROJECT_CONTEXT.md` records local users with LDAP/AD deferred, and frontend auth as not implemented. Build local-user JWT with roles, structured so LDAP can slot in later without a rewrite.
- **Acceptance Criteria:**
  - [ ] Roles defined: admin, operator, viewer — with the permission matrix written down
  - [ ] Passwords hashed with argon2/bcrypt; no plaintext, no reversible storage
  - [ ] Token expiry + refresh; no unbounded-lifetime tokens
  - [ ] Auth provider behind an interface so LDAP is a swap, not a rewrite
  - [ ] Alarm acknowledge and alarm silence are permission-gated and audit-logged with the acting user
- **Dependencies:** `RE-201`, `RE-202`

#### RE-206 — Camera management API
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-20
- **Description:** CRUD for cameras (RTSP URL, credentials, node assignment, enable/disable) plus live health status. Credentials must not be stored in plaintext or logged.
- **Acceptance Criteria:**
  - [ ] CRUD endpoints with validation on RTSP URL format
  - [ ] RTSP credentials encrypted at rest; redacted in all logs and API responses
  - [ ] Per-camera health exposed: connected / FPS / last-frame-age / reconnect count
  - [ ] Camera→node assignment enforced per `PROJECT_CONTEXT.md` distribution
- **Dependencies:** `RE-201`, `RE-202`

---

## 6. Phase 2 — Frontend — `RE-3xx`

> Repo: https://github.com/CodeHub1443/radar-eye-command · Budget: 2 days · **Must run in parallel with `RE-2xx` or the sprint misses.**

#### RE-301 — Frontend/backend API contract freeze
- **Owner:** `@orchestrator`
- **Status:** Todo
- **Priority:** P0
- **Due:** **2026-07-17**
- **Description:** Freeze the API contract before either side starts, so frontend and backend can genuinely proceed in parallel. This task is the enabler for the entire parallel plan in §1.1 — if it slips, the phases serialize and the deadline is gone.
- **Acceptance Criteria:**
  - [ ] OpenAPI spec committed and agreed by `@agent-frontend` and `@agent-backend`
  - [ ] Mock server available so frontend can build without a live backend
  - [ ] Live-video transport decided and recorded (RTSP→WebRTC / HLS / MJPEG snapshot) — this is a real architectural choice with a large latency and CPU delta
- **Dependencies:** `RE-103`, `RE-004`

#### RE-302 — Live camera grid
- **Owner:** `@agent-frontend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-21
- **Description:** Multi-camera live view with detection overlays. Must degrade visibly rather than silently when a stream drops — an operator staring at a frozen frame believing it is live is a safety failure, not a UI bug.
- **Acceptance Criteria:**
  - [ ] Grid renders all in-scope cameras with per-tile connection state
  - [ ] Bounding boxes + class labels overlaid on live tiles
  - [ ] A dead or stalled stream is **unmistakably marked** — greyed out with a visible "SIGNAL LOST" state and last-frame age
  - [ ] Sustained render without leaking memory over a 2h soak
- **Dependencies:** `RE-301`

#### RE-303 — Threat event feed and alarm acknowledge
- **Owner:** `@agent-frontend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-21
- **Description:** Real-time event list with snapshot, class, camera, timestamp, confidence, and Military/Civilian label, plus the operator's acknowledge action. This is the human-in-the-loop surface — the operator confirms or dismisses what the model claims, and that judgement is what the whole system exists to support.
- **Acceptance Criteria:**
  - [ ] Events appear in the feed within 2s of detection
  - [ ] Model confidence is displayed, not hidden — the operator must be able to see when the system is unsure
  - [ ] Acknowledge and dismiss actions recorded to the audit log with user + timestamp
  - [ ] Filter by camera / class / time range
  - [ ] Snapshot opens full-size for verification before the operator acts
- **Dependencies:** `RE-301`

#### RE-304 — Login and session
- **Owner:** `@agent-frontend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-21
- **Description:** `PROJECT_CONTEXT.md` records frontend authentication as not implemented. Wire login, token storage, refresh, logout, and role-gated navigation.
- **Acceptance Criteria:**
  - [ ] Login → token → authorized request round-trip works
  - [ ] Token refresh handled without bouncing the user to login mid-shift
  - [ ] Role-gated routes: viewer cannot reach admin screens
  - [ ] No fonts, scripts, or assets loaded from any CDN — verified with the network unplugged
- **Dependencies:** `RE-205`, `RE-301`

#### RE-305 — System health dashboard
- **Owner:** `@agent-frontend`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-22
- **Description:** Operational view: per-camera state, per-node GPU/CPU/RAM/temp, disk remaining, broker state, pipeline FPS. On an air-gapped box there is no remote monitoring — this screen *is* the monitoring.
- **Acceptance Criteria:**
  - [ ] Per-camera and per-node status visible at a glance
  - [ ] Disk-remaining shown with a warning threshold
  - [ ] Node-down state is loud and obvious (ties to §1.4g / `RE-703`)
- **Dependencies:** `RE-301`, `RE-206`

---

## 7. Phase 2 — AI Integration, Logic & Scoring — `RE-4xx`

#### RE-401 — DeepStream pipeline: RTSP ingest → PGIE → tracker → SGIE → broker
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-21
- **Description:** The core pipeline. `nvurisrcbin` → `nvstreammux` → `nvinfer` (PGIE/YOLO) → `nvtracker` → `nvinfer` (SGIE/ViT, if in scope) → probe → MQTT. Configure `nvurisrcbin` reconnect handling — cameras in a field deployment *will* drop, and DeepStream is known to stall on RTSP EOS if not configured for it.
- **Acceptance Criteria:**
  - [ ] All in-scope cameras ingested concurrently through one pipeline
  - [ ] `nvtracker` enabled with a persistent object ID (NvDCF) — required for `RE-403` de-duplication
  - [ ] Camera unplug → auto-reconnect within 30s **without a process restart**, verified by physically pulling a cable
  - [ ] Pipeline survives a 2h soak with no memory growth and no stalled streams
  - [ ] Detections published to MQTT per the `RE-203` contract
- **Dependencies:** `RE-101`, `RE-203`, `RE-003`

#### RE-402 — ADR-002: Inference stream selection
- **Owner:** `@orchestrator`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-18
- **Description:** Record §1.4f. Dahua/Hikvision expose main + sub streams. Inference on sub-stream (D1/720p) with recording on main stream is the standard pattern and can be the difference between fitting and not fitting on one Orin. Decide with `RE-003` data in hand, not by assumption — note the accuracy cost: small or distant objects (a pistol at range) may be unresolvable at sub-stream resolution, which is exactly the detection that matters most here.
- **Acceptance Criteria:**
  - [ ] `docs/adr/ADR-002-inference-stream.md` committed
  - [ ] Decision backed by the `RE-003` measurement table
  - [ ] Accuracy delta between main and sub stream **measured**, not assumed, for the weapon classes at realistic camera distances
  - [ ] Recording path stated separately from the inference path
- **Dependencies:** `RE-003`

#### RE-403 — Threat scoring and event de-duplication
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-22
- **Description:** Convert raw per-frame detections into meaningful events. Raw YOLO output at 30 FPS produces ~30 events/second per object — unusable. Score, debounce, and consolidate using tracker IDs so one intruder produces one event, not nine hundred. This logic is also the primary defence against false alarms, and false alarms are what get a security system switched off by the people it is meant to protect.
- **Acceptance Criteria:**
  - [ ] Scoring rules documented as a table: class combination → threat level
  - [ ] Requires N-of-M consecutive frames on the same tracker ID before an event fires (configurable)
  - [ ] Per-class confidence thresholds configurable **without a rebuild**
  - [ ] Cooldown window per tracker ID; one sustained presence = one event, not a flood
  - [ ] **False-positive rate measured against recorded real footage** and recorded in this task
  - [ ] Military/Civilian derivation implemented per the `RE-001` decision (ViT vs. rule)
  - [ ] Every alarm-triggering event stores the frame + score that caused it, so an operator can audit any decision after the fact
- **Dependencies:** `RE-401`, `RE-102`, `RE-103`

#### RE-404 — Fire detection tuning
- **Owner:** `@agent-vision`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-22
- **Description:** Fire behaves unlike the weapon classes — no rigid shape, tracker IDs are unstable, and it is highly prone to false positives from sunset, headlights, and reflections. It needs its own thresholds and its own debounce, not the shared path.
- **Acceptance Criteria:**
  - [ ] Separate threshold and debounce path from weapon classes
  - [ ] Tested against footage containing sunset, vehicle headlights, and camp lighting at night
  - [ ] False-positive rate over a full 24h cycle recorded
- **Dependencies:** `RE-403`

---

## 8. Phase 2 — Jetson Deployment — `RE-5xx`

#### RE-501 — Offline deployment bundle
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-23
- **Description:** The target is air-gapped. Every `pip install`, `npm install`, `apt-get`, and `docker pull` that works on the bench will fail in the field. Build a single self-contained installable artifact.
- **Acceptance Criteria:**
  - [ ] One bundle installs the full stack on a fresh Jetson **with networking disabled** — this is the acceptance test, not a formality
  - [ ] All Python wheels, npm packages, and system debs vendored
  - [ ] TRT engines shipped pre-built for the pinned platform, or built on first boot with a documented time cost
  - [ ] Install verified end-to-end on a wiped device at least once before 07-26
  - [ ] Bundle checksum recorded
- **Dependencies:** `RE-006`, `RE-201`, `RE-401`

#### RE-502 — systemd services and watchdog
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-23
- **Description:** Every component must survive reboot and process death unattended. There is nobody to SSH in and restart a dead pipeline at 3am in a camp.
- **Acceptance Criteria:**
  - [ ] Units for: deepstream-pipeline, fastapi, mosquitto, frontend, alarm-controller
  - [ ] `Restart=always` with backoff; dependency ordering correct
  - [ ] All services healthy after a **cold power-cut** (not a graceful reboot) — verified
  - [ ] Watchdog restarts a pipeline that is alive-but-stalled (frames stopped, process still running) — this is the failure mode that `Restart=always` does not catch
  - [ ] `journald` size-capped so logs cannot fill the disk
- **Dependencies:** `RE-501`

#### RE-503 — Jetson power mode and thermal validation
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-23
- **Description:** Bench benchmarks are frequently run at MAXN with active cooling and open air. A field enclosure in Bangladesh ambient is a different thermal environment, and a throttled Orin silently drops FPS — the system appears healthy while missing detections.
- **Acceptance Criteria:**
  - [ ] Power mode explicitly set and pinned via `nvpmodel`; documented
  - [ ] `jetson_clocks` policy decided and recorded
  - [ ] 4h soak at target ambient with `tegrastats` thermal log attached
  - [ ] Zero thermal throttle events, **or** a documented sustained-FPS figure under throttle
  - [ ] Throttle condition surfaces as a health alert (feeds `RE-305`)
- **Dependencies:** `RE-501`, `RE-003`

#### RE-504 — Air-gapped model update procedure
- **Owner:** `@agent-platform`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-24
- **Description:** Models will need retraining after deployment. With no network, that is a physical-media process. Write it down before handover, not after the first request arrives.
- **Acceptance Criteria:**
  - [ ] Documented USB-media procedure: verify → stage → swap engine → restart → validate → roll back
  - [ ] Rollback path tested by actually rolling back
  - [ ] Model artifacts versioned; running version visible in the UI
- **Dependencies:** `RE-502`

---

## 9. Phase 3 — IoT Device — `RE-6xx`

> **Blocked on `RE-002`.** No estimate exists for this phase. If hardware is not in hand on 07-16, this phase de-scopes to `RE-604` under `RE-001`.

#### RE-601 — Relay controller driver
- **Owner:** `@agent-iot`
- **Status:** Blocked
- **Priority:** P0
- **Due:** 2026-07-23
- **Description:** Driver for the `RE-002` device, exposing an interface the alarm policy engine calls. **Fail-safe behaviour is a design requirement, not an afterthought:** define and implement what the relay does when the controlling process dies — a siren stuck on indefinitely is as much a failure as one that never fires.
- **Acceptance Criteria:**
  - [ ] Driver switches siren and beacon independently
  - [ ] Documented, tested behaviour on process death, on power loss, and on boot
  - [ ] Relay state is readable back, not merely commanded — the software must know the real state
  - [ ] Maximum continuous-on duration enforced in the driver as a hard stop
  - [ ] 1000-cycle switching test passed without a stuck relay
- **Dependencies:** `RE-002`

#### RE-602 — Alarm policy engine
- **Owner:** `@agent-backend`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-24
- **Description:** Maps scored threat events to physical alarm actions. Needs cooldown, auto-off, manual override, and manual silence. An alarm that cannot be silenced by the operator on duty will be physically disconnected within a week, and then the system protects nothing.
- **Acceptance Criteria:**
  - [ ] Event→action rules configurable, not hard-coded
  - [ ] Cooldown prevents re-triggering on the same tracker ID
  - [ ] Auto-off after configurable duration
  - [ ] **Manual override and silence always available**, and reachable within one action from the main UI
  - [ ] Every trigger, silence, and override written to the audit log with cause, timestamp, and acting user
  - [ ] Alarm never fires on an unacknowledged Civilian-classified detection alone — escalation path defined per `RE-001`
- **Dependencies:** `RE-601`, `RE-403`, `RE-203`

#### RE-603 — Flashlight / beacon control
- **Owner:** `@agent-iot`
- **Status:** Blocked
- **Priority:** P0
- **Due:** 2026-07-24
- **Description:** Beacon light per the Phase 3 plan. Distinct from the siren — likely different trigger thresholds and different duty behaviour.
- **Acceptance Criteria:**
  - [ ] Beacon controllable independently of siren
  - [ ] Trigger conditions separately configurable
  - [ ] Night-mode behaviour defined (constant vs. flashing)
- **Dependencies:** `RE-601`

#### RE-604 — GPIO stub fallback
- **Owner:** `@agent-iot`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-20
- **Description:** Contingency for `RE-002` slipping. A software-only relay interface with a logging backend, so `RE-602` can be built, tested, and demoed on 07-26 with no physical hardware — and swapped to the real driver later with no changes above the interface.
- **Acceptance Criteria:**
  - [ ] Interface identical to `RE-601`; real driver is a drop-in swap
  - [ ] Stub logs every actuation with timestamp and cause
  - [ ] UI clearly indicates alarm hardware is in **SIMULATED** mode — must never be mistakable for a live alarm
- **Dependencies:** None

---

## 10. Phase 4 — Evaluation — `RE-7xx`

> No estimate exists for this phase in the current plan. It is the acceptance gate for 07-26 — **it needs a real budget, allocated by `RE-001`.**

#### RE-701 — RTSP frame-drop evaluation
- **Owner:** `@agent-qa`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-24
- **Description:** Named explicitly in the Phase 4 plan. Quantify frames lost between camera and inference, and prove the system detects and reports its own blindness.
- **Acceptance Criteria:**
  - [ ] Per-camera frame-drop % measured over 4h at full load
  - [ ] Drop rate under induced network stress recorded
  - [ ] Recovery time after a link drop measured
  - [ ] A stalled stream raises a health alert within 30s — a silently dead camera is the worst failure this system has
  - [ ] Pass/fail threshold agreed with `@tanvir` **before** the test is run, not after
- **Dependencies:** `RE-401`, `RE-502`

#### RE-702 — Detection accuracy evaluation on live camera footage
- **Owner:** `@agent-qa`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-24
- **Description:** Held-out training-set metrics are not field metrics. Evaluate the deployed TRT engine against footage from the real cameras, at real angles, at real distances, in real light — including night. INT8 quantization can degrade small-object recall specifically, which is exactly the pistol-at-range case.
- **Acceptance Criteria:**
  - [ ] ≥1h of labelled footage from the actual deployment cameras, day and night
  - [ ] Per-class precision/recall on the deployed INT8 engine
  - [ ] **Delta measured between held-out-set metrics and live-camera metrics** — if the gap is large, the model is not ready regardless of what the training report said
  - [ ] False-positive rate per camera per 24h recorded
  - [ ] Military/Civilian confusion matrix on real footage, with the civilian→military error rate called out explicitly
- **Dependencies:** `RE-101`, `RE-403`, `RE-501`

#### RE-703 — Node failure and degraded-mode behaviour
- **Owner:** `@agent-qa`
- **Status:** Todo
- **Priority:** P1
- **Due:** 2026-07-25
- **Description:** Covers §1.4g. If Jetson A dies, cameras 1–10 are unmonitored. Full HA is out of scope for 07-26, but the system must not fail *silently* — an operator must know it has gone blind.
- **Acceptance Criteria:**
  - [ ] Node-down is detected and surfaced in the UI within 60s
  - [ ] The affected cameras are shown as unmonitored, not merely offline
  - [ ] Recovery-on-restart verified
  - [ ] Degraded-mode limitation written into the handover documentation
- **Dependencies:** `RE-502`, `RE-305`

#### RE-704 — 24-hour continuous soak
- **Owner:** `@agent-qa`
- **Status:** Todo
- **Priority:** P0
- **Due:** 2026-07-25
- **Description:** The gate before handover. A full day/night cycle at full load on the real hardware. Most failures in this class of system — memory leaks, disk fill, thermal throttle, RTSP stalls, night-time false positives — only appear after hours, and every one of them is invisible in a 20-minute demo.
- **Acceptance Criteria:**
  - [ ] 24h unattended run, zero manual intervention
  - [ ] Zero crashes; zero pipeline restarts
  - [ ] Memory flat, not growing, across the full run
  - [ ] Disk usage tracks the `RE-007` projection
  - [ ] Full-night false-positive count recorded per camera
  - [ ] `tegrastats` log for the full 24h attached
- **Dependencies:** `RE-501`, `RE-502`, `RE-503`, `RE-602`

#### RE-705 — Acceptance test and handover
- **Owner:** `@tanvir`
- **Status:** Todo
- **Priority:** P0
- **Due:** **2026-07-26**
- **Description:** Formal sign-off against the `RE-001` v1 scope. Every deferred item must be written down and communicated, so the delivered system is not mistaken for the documented one.
- **Acceptance Criteria:**
  - [ ] Every `RE-001` IN item demonstrated live on the target hardware
  - [ ] Known limitations documented in writing and handed over, including: no HA, degraded mode behaviour, measured false-positive rate, retention policy, and anything deferred to `RE-9xx`
  - [ ] Operator runbook delivered: start, stop, silence alarm, check health, what to do when a camera dies
  - [ ] `@tanvir` signs acceptance
- **Dependencies:** `RE-704`, `RE-702`, `RE-701`

---

## 11. Deferred Backlog — `RE-9xx`

Not scheduled for 07-26. Recorded so they are not silently forgotten, and so nobody starts them during the sprint.

| ID | Item | Source |
|---|---|---|
| `RE-901` | Second Jetson node + multi-node data topology | Deferred from `RE-004` |
| `RE-902` | LDAP / Active Directory integration | `PROJECT_CONTEXT.md` Future |
| `RE-903` | Tripwire | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-904` | Virtual fence | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-905` | Loitering detection | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-906` | Crowd density | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-907` | Abandoned object | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-908` | Camera blindness detection | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-909` | Cross-camera tracking | `PROJECT_CONTEXT.md` Future Analytics |
| `RE-910` | ViT secondary classifier | Conditional on `RE-001` |
| `RE-911` | Continuous video recording + NVR/NAS | Conditional on `RE-007` |
| `RE-912` | Node HA / automatic failover | Deferred from `RE-703` |

---

## 12. Critical Path

```
RE-001 (scope, TODAY)
  └─> RE-101 (model opt) ─> RE-003 (compute spike) ─> RE-402 (stream ADR)
        └─> RE-401 (pipeline) ─> RE-403 (scoring) ─> RE-602 (alarm policy)
              └─> RE-501 (bundle) ─> RE-502 (systemd) ─> RE-704 (24h soak)
                    └─> RE-705 (acceptance, 07-26)

Parallel track (must not serialize):
  RE-301 (API freeze, 07-17)
    ├─> RE-2xx backend  [@agent-backend]
    └─> RE-3xx frontend [@agent-frontend]
```

**The two tasks that decide whether 07-26 happens: `RE-001` (today) and `RE-003` (by 07-18).** Everything else is downstream of those.

---

## 13. Changelog

| Date | Change | By |
|---|---|---|
| 2026-07-16 | Initial backlog created from `CLAUDE.md`, `AGENTS.md`, `PROJECT_CONTEXT.md`, `threatDetection-architecture.md`, and the existing 4-phase plan | `@orchestrator` |
