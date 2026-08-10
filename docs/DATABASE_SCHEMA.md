# Database Schema

## Purpose

Define persistent data storage for Radar Eye.

---

# cameras

## Description

Registered camera sources. Two independent state groups (RM-12 Camera
Runtime Ownership Refinement): Desired state (`ai_enabled`,
`recording_enabled`) is written exclusively by Camera Registry (the API
service); Observed state (`status` and the fps/latency/last_seen/
reconnect/error fields below) is written exclusively by Camera Runtime
(`apps.deepstream`), persisted directly since the two run as separate
processes and don't share memory. There is no intermediate lifecycle
state machine — a registered camera always wants an active source, and
deletion is the only way a camera stops being desired.

### Fields

id (UUID)
name
location
status
ai_enabled
recording_enabled
fps
latency_ms
last_seen_at
reconnect_count
last_stream_error
created_at
updated_at

---

# camera_stream_profiles

## Description

Camera connection configuration. `rtsp_url_encrypted` is generated
server-side (never operator-entered) from brand + ip_address + port +
stream_path + username + password.

### Fields

id (UUID)
camera_id (FK)
rtsp_url_encrypted
transport
brand
model
ip_address
port
stream_path
username
password_encrypted
created_at
updated_at

---

# camera_calibrations

## Description

Calibration data for distance estimation.

### Fields

id (UUID)
camera_id (FK)
homography_matrix
reference_points
calibrated_by
created_at

---

# incidents

## Description

Primary incident records.

### Fields

id (UUID)

camera_id (FK)

track_id

incident_type

threat_level

status

threat_summary

created_at

updated_at

resolved_at

### Example Threat Summary

{
  "weapon": "ranged_lethal",
  "uniform": "civilian",
  "zone": "zone_1",
  "rule_id": "RANGED_LETHAL_ZONE_1"
}

---

# incident_events

## Description

Incident lifecycle and audit history.

### Fields

id (UUID)

incident_id (FK)

event_type

event_payload

created_at

---

# human_review_items

## Description

Threats requiring operator review.

Generated when:

uniform == unknown

### Fields

id (UUID)

camera_id (FK)

track_id

reason

status

resolution

resolved_by

created_at

resolved_at

### Status Values

OPEN

CONFIRMED_MILITARY

CONFIRMED_CIVILIAN

ESCALATED

DISMISSED

---

# snapshots

## Description

Snapshot metadata.

### Fields

id (UUID)

incident_id (FK)

camera_id (FK)

file_path

captured_at

---

# recordings

## Description

Event clip metadata.

### Fields

id (UUID)

incident_id (FK)

camera_id (FK)

file_path

start_time

end_time

created_at

---

# system_events

## Description

Operational events.

### Fields

id (UUID)

event_type

severity

payload

created_at

---

# users

## Description

System users.

### Fields

id (UUID)

username

password_hash

role

created_at

---

# audit_log

## Description

User action audit history (ADR-008). Distinct from ``incident_events``
(incident-lifecycle history, scoped to a single incident) and
``system_events`` (operational/runtime events, not tied to a user action).
``audit_log`` records who did what: every operator/admin-initiated
mutation across the system, independent of whether it relates to an
incident at all (e.g. a camera update, a config change, a user-management
action).

### Fields

id (UUID)

actor_user_id (FK -> users.id, nullable for system-generated actions)

action

resource_type

resource_id

details (JSONB)

timestamp

---

# Relationships

camera
├── camera_stream_profiles
├── camera_calibrations
├── incidents
└── human_review_items

incident
├── incident_events
├── snapshots
└── recordings

user
└── audit_log

---

# Persistence Strategy

## Transient Processing Data

The following are processed in memory only:

- Video frames
- Object detections
- Tracking data
- Intermediate classifier outputs
- Per-frame distance estimates
- Per-frame threat assessments

Reason:

Transient processing artifacts with high storage cost and low operational value.

---

## Persisted Data

Store:

- Cameras
- Camera Profiles
- Calibrations
- Incidents
- Incident History
- Human Review Items
- Snapshots
- Event Clips
- System Events
- Users
- Audit Log

---

# Explicit Non-Persistence Rules

DO NOT STORE:

- Raw frames
- Frame-level metadata
- Detection history
- Tracking history
- Per-frame analytics

STORE ONLY:

- Incident records
- Human review records
- Evidence metadata
- Audit history
- Configuration

---

# Recording Storage Layout

/recordings/
    camera_id/
        YYYY-MM-DD/
            continuous/
            events/

/snapshots/
    camera_id/
        YYYY-MM-DD/

Database stores metadata only.

Filesystem stores actual media files.

---

# Incident Deduplication Constraint

Rule:

1 Track = 1 Active Incident

Constraint:

(camera_id, track_id)

must map to a single active incident.

Reason:

Prevent duplicate incidents for the same tracked subject.