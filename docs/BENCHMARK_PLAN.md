# Benchmark Plan

## Purpose

Validate that the selected architecture can satisfy operational requirements before implementation.

---

# 1. Detector Benchmark

## Component
YOLO26 Weapon Detector

## Metrics
- mAP50
- Precision
- Recall
- False Positives / Hour
- Inference Latency
- FPS

## Test Conditions
- Day
- Night
- Rain
- Fog
- Partial Occlusion

## Acceptance Criteria
TBD

---

# 2. Uniform Classifier Benchmark

## Component
ViT Military/Civilian Classifier

## Metrics
- Accuracy
- Precision
- Recall
- F1
- Unknown Rate

## Test Conditions
- Front View
- Side View
- Rear View
- Partial Body
- Low Light

## Acceptance Criteria
TBD

---

# 3. Tracker Benchmark

## Component
NvDCF

## Metrics
- IDF1
- ID Switches
- Track Stability
- Lost Track Rate

## Acceptance Criteria
TBD

---

# 4. Distance Estimation Benchmark

## Component
Ground Plane Projection

## Metrics
- Mean Distance Error
- Max Distance Error

## Zones
- 0–20m
- 20–50m
- 50m+

## Acceptance Criteria
TBD

---

# 5. Threat Engine Benchmark

## Metrics
- Classification Accuracy
- Rule Consistency

## Acceptance Criteria
TBD

---

# 6. Multi-Camera DeepStream Benchmark

## Hardware
Jetson AGX Orin 32GB

## Metrics
- Camera Count
- GPU Utilization
- CPU Utilization
- Memory Usage
- End-to-End Latency

## Acceptance Criteria
TBD

---

# 7. Recording Benchmark

## Metrics
- Storage Consumption
- Recording Stability
- Clip Extraction Latency

## Acceptance Criteria
TBD

---

# 8. Database Benchmark

## Component
PostgreSQL

## Metrics
- Insert Throughput
- Query Latency

## Acceptance Criteria
TBD

---

# Benchmark Exit Criteria

All acceptance criteria satisfied before implementation begins.