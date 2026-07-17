# Radar Eye Agent System
## AGENTS.md file

## Authority Chain

Human (Tanvir)
    ->
Orchestrator
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

---

## Development Rules

Every task must have:

- Owner
- Description
- Acceptance Criteria
- Dependencies

Every change must originate from a task.

No code may be written without a task.
