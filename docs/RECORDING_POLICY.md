# Recording Policy

## Purpose

Define video retention, recording behavior, and event clip generation.

---

# Recording Modes

## Continuous Recording

Enabled: YES

Description:
All camera streams are continuously recorded.

---

# Event Recording

Enabled: YES

Description:
Incidents generate event clips.

---

# Event Clip Configuration

Pre-Event Buffer:
10 seconds

Post-Event Buffer:
20 seconds

Total Clip Length:
30 seconds

---

# Video Encoding

Primary Format:
H.265

Purpose:
Storage efficiency

---

# Playback Format

Supported:
H.264
H.265

---

# Retention Policy

Continuous Recording:
30 days

Incident Clips:
30 days

Snapshots:
30 days

---

# Storage Management

When storage threshold exceeded:

1. Delete oldest recordings
2. Preserve active incidents
3. Preserve unresolved incidents

---

# Future Enhancements

- Tiered storage
- NAS support
- Cloud archival