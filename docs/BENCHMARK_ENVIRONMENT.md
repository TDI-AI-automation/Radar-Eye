# Radar Eye Benchmark Environment

## Hardware

### Jetson

Model:

Jetson AGX Orin 32GB

Quantity:

2

---

## Cameras

Type:

Dahua / Hikvision

Stream:

RTSP

Codec:

H.264

Resolution:

4MP

Frame Rate:

30 FPS

---

## Software

DeepStream:

Required

Status:

MANDATED

---

TensorRT:

Required

Status:

MANDATED

---

CUDA:

Required

Status:

MANDATED

---

## Benchmark Rules

### Rule 1

All benchmarks must use production hardware.

---

### Rule 2

All benchmarks must use production camera streams.

---

### Rule 3

Synthetic benchmark results must be clearly labeled.

---

### Rule 4

All benchmark runs must record:

- GPU utilization
- CPU utilization
- Memory utilization
- Throughput
- Latency

---

### Rule 5

Every benchmark result must be reproducible.

---

### Rule 6

Every benchmark must generate a benchmark report.

---

## Output Artifacts

Required:

- Benchmark configuration
- Raw measurements
- Final report
- Pass / Fail result