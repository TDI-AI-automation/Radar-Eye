# Radar Eye Runtime Flow

## Normal Detection Flow

RTSP Camera

↓

Video Ingestion

↓

Decode

↓

DeepStream Pipeline

↓

TensorRT Inference

↓

Detection

↓

Threat Assessment

↓

Alert Management

↓

Operator UI

---

## Alarm Flow

Threat

↓

Alert

↓

Alarm Management

↓

Alarm Device

---

## Recording Flow

RTSP Stream

↓

Recording Management

↓

Retention Storage

---

## Audit Flow

User Action

↓

Audit Management

↓

Audit Storage

---

## Health Flow

Runtime Components

↓

Monitoring & Health

↓

Operator Dashboard

---

## Failure Recovery Flow

Camera Failure

↓

Stream Health Detection

↓

Reconnect Attempt

↓

Camera Restored

OR

↓

Camera Offline Event