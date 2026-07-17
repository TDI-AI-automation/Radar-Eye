# Radar Eye Benchmark Backlog

## B-001

Benchmark:

Jetson AGX Orin Camera Capacity

Goal:

Determine sustainable camera count per Jetson.

Inputs:

- RTSP streams
- DeepStream pipeline
- Production resolution

Measures:

- FPS
- GPU utilization
- CPU utilization
- Memory utilization
- Stability

Reference:

V-001

Status:

PENDING

---

## B-002

Benchmark:

Object Detection Throughput

Goal:

Determine maximum detection throughput.

Inputs:

- Candidate detection model

Measures:

- FPS
- Latency
- GPU utilization

Reference:

V-002

Status:

PENDING

---

## B-003

Benchmark:

Threat Classification Throughput

Goal:

Determine classification overhead.

Inputs:

- Candidate classification model

Measures:

- Latency
- GPU utilization
- Memory utilization

Reference:

V-002

Status:

PENDING

---

## B-004

Benchmark:

YOLO + ViT Combined Pipeline

Goal:

Validate combined pipeline performance.

Measures:

- End-to-end latency
- Throughput
- GPU utilization
- Stability

Reference:

A-002

Status:

PENDING

---

## B-005

Benchmark:

Zero-Copy Verification

Goal:

Identify GPU↔CPU transfers.

Measures:

- Transfer count
- Transfer locations

Reference:

V-004

Status:

PENDING

---

## B-006

Benchmark:

20-Camera End-to-End Test

Goal:

Validate deployment assumptions.

Measures:

- Stability
- Alert latency
- Resource utilization

Reference:

V-005

Status:

PENDING

---

## B-007

Benchmark:

Failure Recovery Test

Goal:

Validate automatic recovery behavior.

Measures:

- Recovery time
- Service continuity

Reference:

V-009

Status:

PENDING

---

## B-008

Benchmark:

Storage Retention Sizing

Goal:

Validate 30-day retention requirements.

Measures:

- Required storage
- Growth rate

Reference:

V-003

Status:

PENDING