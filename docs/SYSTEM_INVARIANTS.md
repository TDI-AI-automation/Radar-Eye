# Radar Eye System Invariants

## INV-001

All camera streams originate from RTSP sources.

---

## INV-002

All video inference executes through DeepStream pipelines.

---

## INV-003

All AI models execute through TensorRT engines in production.

---

## INV-004

System must operate without internet connectivity.

---

## INV-005

No cloud dependency exists for runtime operation.

---

## INV-006

Every alert must be traceable to at least one threat event.

---

## INV-007

Every threat event must be traceable to at least one detection.

---

## INV-008

Every detection must be traceable to a camera source.

---

## INV-009

All user actions affecting configuration must generate audit records.

---

## INV-010

Authentication is required for all operator and administrator access.

---

## INV-011

Video retention must preserve recordings for the configured retention period.

---

## INV-012

Failure of a single camera must not stop processing of other cameras.

---

## INV-013

Failure of one AI pipeline instance must not crash the entire system.

---

## INV-014

System time must be available for event ordering and auditing.

---

## INV-015

Zero-copy processing is preferred wherever technically possible and deviations must be justified.