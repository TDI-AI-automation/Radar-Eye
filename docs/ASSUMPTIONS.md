# Radar Eye Assumptions

## Purpose

This document records assumptions that have not yet been validated.

Assumptions are not facts.

Every assumption must eventually become either:

- VALIDATED
- REJECTED

---

## A-001

Assumption:

One Jetson AGX Orin 32GB can process 10 cameras simultaneously.

Status:

UNVALIDATED

Validation Method:

Benchmark on real hardware.

---

## A-002

Assumption:

YOLO + ViT can run simultaneously within performance targets.

Status:

UNVALIDATED

Validation Method:

Benchmark on real hardware.

---

## A-003

Assumption:

30-day retention is achievable within available storage resources.

Status:

UNVALIDATED

Validation Method:

Storage sizing exercise.

---

## A-004

Assumption:

Zero-copy architecture can be maintained through the full AI pipeline.

Status:

UNVALIDATED

Validation Method:

Architecture review and implementation verification.

---

## A-005

Assumption:

Two Jetsons are sufficient for the initial deployment.

Status:

UNVALIDATED

Validation Method:

Capacity testing.

---

## A-006

Assumption:

Real-time alerting requirements can be met without introducing a dedicated event bus.

Status:

UNVALIDATED

Validation Method:

Architecture review.

---

## A-007

Assumption:

Local-only operation satisfies operational requirements.

Status:

UNVALIDATED

Validation Method:

Stakeholder confirmation.

---

## A-008

Assumption:

Current camera infrastructure provides sufficient image quality for weapon detection.

Status:

UNVALIDATED

Validation Method:

Field testing.