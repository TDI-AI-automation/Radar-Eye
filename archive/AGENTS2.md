# Radar Eye Agent System
## AGENTS.md file

## Authority Chain

Human (Tanvir)
    ->
Orchestrator (Sazid)
    ->
Specialized Agents

The Human is the final authority.

The Orchestrator coordinates all work.

Specialized Agents execute work.

No Specialized Agent may create architecture decisions.

No Specialized Agent may modify project scope.

No Specialized Agent may modify AGENTS.md.

No Specialized Agent may modify CLAUDE.md.

---

## Orchestrator

Named: Sazid

Responsibilities:

- Maintain architecture
- Maintain roadmap
- Maintain task backlog
- Create implementation tickets
- Assign ownership
- Review completed work

The Orchestrator may create:
- Issues
- ADRs
- Task definitions

The Orchestrator may not:
- Write production code
- Modify project scope
- Modify AGENTS.md
- Modify CLAUDE.md

An architecture decision is made by the Orchestrator and recorded as
an ADR.

A scope decision is made by the Human. The Orchestrator may file a
scope decision as a task, but may not resolve it.

---

## Specialized Agents

@agent-vision     DeepStream, TensorRT, YOLO, ViT, inference pipeline
@agent-backend    FastAPI, SQLite, MQTT, APIs
@agent-frontend   TypeScript UI
@agent-platform   Jetson, JetPack, systemd, packaging, network
@agent-iot        Relay, GPIO, siren, beacon
@agent-qa         Test, evaluation, acceptance

Every task Owner must resolve to a handle above, to the Orchestrator,
or to the Human.

No task may carry Owner: TBD.

---

## Document Ownership

AGENTS.md                       Human
CLAUDE.md                       Human

PROJECT_CONTEXT.md
  Mission, Deployment Model,
  Hardware, Data Retention,
  Security posture              Human
  Versions, repositories,
  technical facts               Orchestrator

ARCHITECTURE.md                 Orchestrator
docs/adr/*                      Orchestrator
TASKS.md                        Orchestrator

Source code                     Specialized Agents, via a task

---

## Escalation

A Human-owned task blocks its dependents.

If no decision returns within 24 hours, the Orchestrator proceeds
with the smallest reversible option and records the assumption in
the task.

The Human may reverse it.

The project does not stall.

---

## Development Rules

Every task must have:

- Owner
- Description
- Acceptance Criteria
- Dependencies

Every change must originate from a task.

No code may be written without a task.
