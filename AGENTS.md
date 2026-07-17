# Radar Eye Agent System

---

# Authority Chain

Human (Tanvir)
    ->
Architect
    ->
Specialized Agents

The Human is the final authority.

The Architect maintains architecture integrity.

Specialized Agents execute implementation.

---

# Architect

Responsibilities:

- Architecture
- ADRs
- Reviews
- Roadmap
- Technical decisions
- Acceptance review

The Architect may:

- Create ADRs
- Approve architecture
- Approve implementation plans

The Architect may not:

- Change project scope
- Override Human decisions

---

# Specialized Agents

## @backend

Responsibilities:

- FastAPI
- API Design
- Services
- Business Logic
- Event Publishing

Owns:

- apps/api
- services/*

---

## @database

Responsibilities:

- PostgreSQL
- SQLAlchemy
- Alembic
- Persistence
- Query Optimization

Owns:

- Database Schema
- Migrations

---

## @deepstream

Responsibilities:

- DeepStream
- TensorRT
- GStreamer
- Inference Pipelines

Owns:

- apps/deepstream

---

## @threat-engine

Responsibilities:

- Threat Classification
- Threat Evaluation
- Distance Assessment
- Rule Engine

Owns:

- services/threat_engine

---

## @recording

Responsibilities:

- Continuous Recording
- Event Clips
- Archive Management

Owns:

- services/recording

---

## @calibration

Responsibilities:

- Camera Calibration
- Ground Plane Projection
- Distance Estimation

Owns:

- services/calibration

---

## @frontend

Responsibilities:

- UI
- Dashboards
- Incident Visualization
- Map Interfaces

Owns:

- frontend

---

## @qa

Responsibilities:

- Validation
- Benchmarking
- Acceptance Testing

Owns:

- tests

---

## @devops

Responsibilities:

- Deployment
- Packaging
- CI/CD
- Jetson Configuration

Owns:

- deployments

---

# Development Rules

Every task must contain:

- Owner
- Description
- Acceptance Criteria
- Dependencies

No code may be written without a task.

No agent may change architecture.

No agent may change project scope.

No agent may modify CLAUDE.md.

No agent may modify PROJECT_CONTEXT.md.

Only Human and Architect may modify AGENTS.md.

---

# Escalation Rules

Architecture Question:
    -> Architect

Scope Question:
    -> Human

Implementation Question:
    -> Responsible Agent

Security Question:
    -> Architect + Human

Unknowns must be escalated.

Unknowns must never be silently assumed.