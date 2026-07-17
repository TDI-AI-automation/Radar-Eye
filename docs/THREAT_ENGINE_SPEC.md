# Threat Engine Specification

## Inputs

### Detector Output

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

### Uniform Classification

- military
- civilian
- unknown

### Distance Zone

- zone_1 (0–20m)
- zone_2 (20–50m)
- zone_3 (50m+)

---

## Threat Levels

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

---

## Rules

| Uniform | Weapon | Zone | Threat |
|----------|---------|---------|---------|
| military | any weapon | any | ALLY |
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

## Threat Escalation Rules

TBD

---

## Threat De-escalation Rules

TBD

---

## Human Review Rules

TBD