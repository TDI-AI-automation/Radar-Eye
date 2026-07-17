# Radar Eye Requirement Conflicts

## RC-001

Requirement Source:

REQUIREMENTS.md

Requirement:

Detect

- Person
- Rifle
- RPG
- Pistol
- Fire

---

Observed Model Capability:

yolo26m_weapon.pt

Classes:

- melee_lethal
- non_lethal
- ranged_lethal

---

Conflict:

Current detector output does not match documented requirements.

---

Possible Resolutions:

Option A

Update requirements to match model.

Status:

NOT DECIDED

---

Option B

Retrain detector to match requirements.

Status:

NOT DECIDED

---

Option C

Use detector as Stage-1 model and add additional models.

Status:

NOT DECIDED

---

Priority:

HIGH