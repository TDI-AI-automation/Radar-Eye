## CLAUDE.md file

# Radar Eye

Military AI Surveillance Platform

## Mission

Detect and classify threats from RTSP camera streams
running on NVIDIA Jetson AGX Orin edge devices.

## Deployment

- Air-gapped
- Offline-first
- Local-only operation
- Bangladesh military deployment

## Hardware

- 2 x NVIDIA Jetson AGX Orin 32GB
- 20 cameras
- Dahua/Hikvision
- 4MP
- H264
- RTSP

## AI Pipeline

DeepStream 7.0

Primary:
- YOLO

Secondary:
- ViT Classifier

Threat Classes:
- Military
- Civilian

Detected Objects:
- Person
- Rifle
- RPG
- Pistol
- Fire

## Technology Decisions

Frontend:
- TypeScript

Backend:
- FastAPI

Database:
- SQLite WAL

Messaging:
- MQTT (Mosquitto)

Authentication:
- JWT + RBAC

## Development Rules

- No direct commits to main
- Use feature branches
- Architecture decisions require ADR
- DeepStream is mandatory
- TensorRT deployment required
