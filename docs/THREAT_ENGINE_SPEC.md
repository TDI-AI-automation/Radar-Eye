# Threat Engine Specification

## Purpose

The Threat Engine is responsible for converting detector outputs, classifier outputs, and distance estimation results into operational decisions.

The Threat Engine is the authoritative source of:

- Threat Levels
- Incident Creation Decisions
- Alarm Decisions
- Human Review Decisions

---

# Inputs

## Detector Output

Supported Classes:

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

---

## Uniform Classification

Supported Classes:

- military
- civilian
- unknown

---

## Distance Zones

### Zone 1

Distance:

0m – 20m

---

### Zone 2

Distance:

20m – 50m

---

### Zone 3

Distance:

50m+

---

# Threat Levels

The Threat Engine produces one of the following outcomes:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH
- HUMAN_REVIEW

---

# Classification Rules

| Uniform | Weapon | Zone | Threat |
|----------|----------|----------|----------|
| military | any | any | ALLY |
| civilian | none | any | OBSERVE |
| civilian | non_lethal | any | LOW |
| civilian | melee_lethal | zone_3 | LOW |
| civilian | melee_lethal | zone_2 | MEDIUM |
| civilian | melee_lethal | zone_1 | HIGH |
| civilian | ranged_lethal | zone_3 | MEDIUM |
| civilian | ranged_lethal | zone_2 | HIGH |
| civilian | ranged_lethal | zone_1 | HIGH |
| unknown | any | any | HUMAN_REVIEW |
| any | fire | any | HIGH |

---

# Threat Escalation Policy

## HIGH

Trigger:

3 consecutive frames classified as HIGH.

Action:

Generate:

ThreatAssessmentEvent

---

If HIGH persists for:

1 second

Generate:

IncidentCreatedEvent

---

If HIGH persists for:

3 seconds

Trigger:

AlarmRequestedEvent

---

## MEDIUM

If MEDIUM persists for:

2 seconds

Generate:

IncidentCreatedEvent

---

## LOW

No incident creation.

No alarm generation.

Visible in dashboard only.

---

## FIRE

Immediately classified as HIGH.

Immediately generates:

- ThreatAssessmentEvent
- IncidentCreatedEvent
- AlarmRequestedEvent

No waiting period.

---

# Threat De-escalation Policy

## HIGH

Threat must be absent for:

10 seconds

Before downgrade.

---

## MEDIUM

Threat must be absent for:

5 seconds

Before downgrade.

---

## LOW

Threat must be absent for:

3 seconds

Before downgrade.

---

# Human Review Workflow

## Trigger Conditions

Human Review is required when:

- uniform == unknown

---

## Threat Output

Threat Level:

HUMAN_REVIEW

---

## Incident Creation

No incident created automatically.

---

## Alarm Creation

No alarm created automatically.

---

## Review Queue

System creates:

HumanReviewItem

---

## Operator Actions

Operator may:

- Confirm Military
- Confirm Civilian
- Escalate
- Dismiss

---

# Incident Creation Policy

## Create Incident

Threat Levels:

- HIGH
- MEDIUM

---

## Do Not Create Incident

Threat Levels:

- ALLY
- OBSERVE
- LOW
- HUMAN_REVIEW

---

# Incident Deduplication Policy

Rule:

1 Track = 1 Active Incident

---

## Existing Incident Reuse

If:

camera_id
+
track_id

already has an active incident

THEN:

Update existing incident.

Do not create another incident.

---

## Incident Closure

Incident closes when:

Track lost for more than 10 seconds

OR

Operator manually closes incident.

---

# Alarm Policy

## Alarm Eligible

Threat Levels:

- HIGH

---

## Not Alarm Eligible

Threat Levels:

- MEDIUM
- LOW
- ALLY
- OBSERVE
- HUMAN_REVIEW

---

## Fire

Always alarm eligible.

Immediate trigger.

---

# Rule Auditability

Every ThreatAssessmentEvent must contain:

{
  "rule_id": "string",
  "weapon_type": "string",
  "uniform": "string",
  "zone": "string",
  "threat_level": "string"
}

Reason:

All threat decisions must be explainable and auditable.

---

# Determinism Requirement

The Threat Engine must be deterministic.

Identical inputs must always produce identical outputs.

No probabilistic business logic is permitted.

No AI-generated threat decisions are permitted.

Only approved rules defined in this document may determine threat outcomes.