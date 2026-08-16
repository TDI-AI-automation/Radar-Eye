# Radar Eye Open Questions

## Q-001

Question:

What is the maximum acceptable end-to-end alert latency?

Status:

OPEN

Owner:

Client

---

## Q-002

Question:

What detection accuracy is required for weapon detection?

Status:

OPEN

Owner:

Client

---

## Q-003

Question:

What detection accuracy must be maintained across:

- Zone 1 (0–20m)
- Zone 2 (20–50m)
- Zone 3 (50m+)

Status:

PARTIALLY RESOLVED

Owner:

Client

Notes:

Distance zones have been defined:

- Zone 1 = 0–20m
- Zone 2 = 20–50m
- Zone 3 = 50m+

Required detection performance per zone remains unknown.

---

## Q-004

Question:

What storage hardware will be available?

Status:

OPEN

Owner:

Client

---

## Q-005

Question:

What siren and GPIO relay hardware models will be integrated in future phases?

Status:

PARTIALLY RESOLVED

Owner:

Client

Notes:

Alert architecture shall support:

- UI
- SMS
- Email
- WhatsApp
- GPIO Relay
- Audio Siren

Phase 1 implementation:

- UI only

Specific siren and relay hardware models remain unknown.

Ownership resolved by ADR-029:

UI/SMS/Email/WhatsApp are owned by Alert Service (Phase 6); GPIO Relay/Audio Siren (and floodlight/PTZ) are owned by Hardware Action Service (Phase 7), consuming Alert Service's `AlertRaisedEvent`. This resolves *which service* owns each channel — the specific hardware models remain the still-open part of this question.

---

## Q-006

Question:

Will a central command server exist in addition to the two Jetsons?

Status:

OPEN

Owner:

Client

---

## Q-007

Question:

What frontend live-streaming protocol is required?

Status:

CLOSED

Answer:

HLS (`hlssink2`), replacing an earlier WebRTC (`webrtcbin`) implementation
per ADR-031. Implemented and hardware-validated (Live Monitoring's single
AI-annotated video output). See ADR-030/ADR-031 and
`docs/DEEPSTREAM_PIPELINE_SPEC.md` Stage 5.5 for the owning
service (DeepStream itself, not a separate Live Streaming process) and
`docs/FRONTEND_BACKEND_CONTRACTS.md`'s Live Monitoring / HLS Video
Delivery section for the request/response contract.

---

## Q-008

Question:

What audit and compliance requirements exist?

Status:

OPEN

Owner:

Client

---

## Q-009

Question:

What user roles are required beyond Administrator and Operator?

Status:

OPEN

Owner:

Client

---

## Q-010

Question:

What availability target is required?

Status:

OPEN

Owner:

Client

---

## Q-011

Question:

What confidence threshold should trigger Human Review?

Status:

OPEN

Owner:

TDI

Notes:

Classification outcomes:

- Military
- Civilian
- Unknown

Unknown classifications shall be routed to Human Review.

Confidence threshold remains undefined.

---

## Q-012

Question:

What end-to-end alert latency is acceptable for HIGH threats?

Status:

OPEN

Owner:

Client

---

## Q-013

Question:

What calibration accuracy is required for zone assignment?

Status:

OPEN

Owner:

TDI

Notes:

Distance estimation method has been selected:

- Ground Plane Calibration
- Ground Plane Projection

Required accuracy tolerance remains undefined.

---

## Q-014

Question:

What is the persistence model for system configuration (`GET`/`PATCH /config`,
docs/FRONTEND_BACKEND_CONTRACTS.md's Settings section)?

Status:

OPEN

Owner:

Engineering

Notes:

ADR-008 lists "configuration" as one of four persisted categories (alongside
incidents, evidence metadata, and audit history), but neither
`docs/DATABASE_SCHEMA.md` nor `docs/DOMAIN_MODEL.md` defines its shape --
unlike audit history, which had a `docs/DOMAIN_MODEL.md` "Audit Log" entity
to anchor a schema on (see `audit_log`, added during RM-12 Phase 2), there
is no equivalent "Config"/"SystemConfig" conceptual entity anywhere.

Discovered during RM-12 Phase 4 (`docs/RM-12_IMPLEMENTATION_PLAN.md`):
`GET`/`PATCH /config` were explicitly descoped from RM-12 rather than
guessed at, per the Principal Engineer's explicit instruction --
implementing them would require inventing a configuration persistence
model (ownership, validation, storage semantics, versioning, rollback)
rather than implementing already-approved architecture. A future
Configuration Management milestone must resolve this design question
before `GET`/`PATCH /config` can be implemented. No placeholder route, no
YAML write-back, and no new table were added in the meantime.

---

## Q-015

Question:

What does the `/ws/tracking` WebSocket channel actually carry
(docs/FRONTEND_BACKEND_CONTRACTS.md's Tactical Map section)?

Status:

OPEN

Owner:

Engineering

Notes:

Unlike every other `/ws/*` channel, `/ws/tracking` has no named event model
anywhere -- `docs/FRONTEND_BACKEND_CONTRACTS.md`'s "Frontend Event Models"
section defines a shape for every other channel's event(s) but has no
"Tracking" entry, and none of the 10 existing `EventEnvelope` payloads in
`shared/events/payloads.py` carries per-track position data.

Discovered during RM-12 Phase 5 (`docs/RM-12_IMPLEMENTATION_PLAN.md`,
which itself flagged this channel as needing a clarifying question before
implementation, unlike the plan's other five channels).
`docs/RM-12_IMPLEMENTATION_PLAN.md`'s Phase 5. Explicitly descoped from
RM-12 per the Principal Engineer's instruction, rather than inventing a
payload/publisher/schema unilaterally. A future Tracking Streaming
milestone must define: the event schema, the payload contract, the
publication frequency, publisher ownership (presumably DeepStream's
Runtime Adapter), the frontend consumption model, lifecycle semantics, and
how this interacts with `docs/DATABASE_SCHEMA.md`'s Explicit
Non-Persistence Rules (tracking history must never be stored -- this would
be the first bus-transported data that is neither a debounced state-change
event like every other channel nor persisted anywhere). No placeholder
event type, payload, or route was added in the meantime.