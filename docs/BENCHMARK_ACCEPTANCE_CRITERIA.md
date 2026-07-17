# Benchmark Acceptance Criteria

## Detector

Precision >= 90%

Recall >= 90%

False Positives:
<= 5 per hour per camera

---

## Uniform Classifier

Accuracy >= 95%

Unknown Classification:
<= 10%

---

## Tracker

IDF1 >= 85%

Track Loss Rate <= 10%

---

## Distance Estimation

Error @ 20m:
<= 2m

Error @ 50m:
<= 5m

---

## Threat Engine

Rule Consistency:
100%

---

## DeepStream Performance

Target Cameras:
10 per Jetson

GPU Utilization:
<= 85%

Memory Utilization:
<= 85%

---

## Alert Latency

Threat Detection to UI Alert:

<= 2 seconds

---

## Recording

Clip Extraction Success:

100%

---

## System Availability

Continuous Operation:

24 hours without failure