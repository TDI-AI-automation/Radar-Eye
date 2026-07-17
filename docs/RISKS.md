# Radar Eye Risks

## R-001

Risk:

One Jetson cannot sustain 10-camera workload.

Impact:

High

Mitigation:

Benchmark before implementation.

---

## R-002

Risk:

YOLO + ViT exceeds latency budget.

Impact:

High

Mitigation:

Benchmark before architecture decisions are finalized.

---

## R-003

Risk:

30-day retention exceeds available storage.

Impact:

High

Mitigation:

Perform storage sizing before storage architecture selection.

---

## R-004

Risk:

Zero-copy architecture breaks due to component incompatibility.

Impact:

High

Mitigation:

Verify memory ownership and data movement before implementation.

---

## R-005

Risk:

RTSP stream instability causes pipeline failures.

Impact:

High

Mitigation:

Design reconnect and health-monitoring strategy.

---

## R-006

Risk:

Weapon detection accuracy is insufficient at operational distances.

Impact:

High

Mitigation:

Field validation using actual cameras and deployment conditions.

---

## R-007

Risk:

DeepStream version compatibility issues.

Impact:

Medium

Mitigation:

Freeze supported software stack before implementation.

---

## R-008

Risk:

Multi-node synchronization complexity is underestimated.

Impact:

Medium

Mitigation:

Design topology before selecting technologies.

---

## R-009

Risk:

Alarm hardware integration requirements change.

Impact:

Medium

Mitigation:

Treat alarm subsystem as a separate interface-driven component.

---

## R-010

Risk:

Frontend live-video strategy introduces unexpected latency.

Impact:

Medium

Mitigation:

Evaluate transport architecture before implementation.