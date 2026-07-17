# Radar Eye Failure Scenarios

## FS-001

Failure:

Single Camera Offline

Expected Behavior:

- Camera marked offline
- Event generated
- Other cameras continue operating

---

## FS-002

Failure:

Multiple Cameras Offline

Expected Behavior:

- Offline events generated
- Impact isolated to affected cameras

---

## FS-003

Failure:

RTSP Connection Loss

Expected Behavior:

- Reconnect attempts initiated
- Offline state entered after threshold

---

## FS-004

Failure:

Inference Pipeline Crash

Expected Behavior:

- Failed pipeline restarted
- Other pipelines continue operating

---

## FS-005

Failure:

Threat Engine Failure

Expected Behavior:

- Error recorded
- Detection processing protected from crash propagation

---

## FS-006

Failure:

Alert Engine Failure

Expected Behavior:

- Threat events retained
- Alert generation resumes after recovery

---

## FS-007

Failure:

Recording Storage Full

Expected Behavior:

UNKNOWN

Reference:

Q-004

---

## FS-008

Failure:

Node Reboot

Expected Behavior:

- Services automatically recover
- Processing resumes

---

## FS-009

Failure:

Jetson-A Failure

Expected Behavior:

UNKNOWN

Reference:

A-005

---

## FS-010

Failure:

Jetson-B Failure

Expected Behavior:

UNKNOWN

Reference:

A-005

---

## FS-011

Failure:

Alarm Hardware Failure

Expected Behavior:

UNKNOWN

Reference:

Q-005

---

## FS-012

Failure:

Authentication Service Failure

Expected Behavior:

- Failure recorded
- Unauthorized access prevented

---

## FS-013

Failure:

Audit Service Failure

Expected Behavior:

UNKNOWN

---

## FS-014

Failure:

Monitoring Service Failure

Expected Behavior:

Core surveillance functions continue operating.

---

## Rule

No single camera failure may stop surveillance processing for other cameras.