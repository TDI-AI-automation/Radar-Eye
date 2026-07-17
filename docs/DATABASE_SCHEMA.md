# Database Schema

## Purpose

Define persistent data storage for Radar Eye.

---

# cameras

## Description

Registered camera sources.

### Fields

id (UUID)
name
location
status
created_at
updated_at

---

# camera_stream_profiles

## Description

Camera connection configuration.

### Fields

id (UUID)
camera_id (FK)
rtsp_url_encrypted
transport
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
  "rule": "RANGED_LETHAL_ZONE_1"
}

---

# incident_events

## Description

Incident state transitions and audit history.

### Fields

id (UUID)
incident_id (FK)
event_type
event_payload
created_at

---

# snapshots

## Description

Incident snapshot metadata.

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

System operational events.

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

# Relationships

camera
    ├── camera_stream_profiles
    ├── camera_calibrations
    └── incidents

incident
    ├── incident_events
    ├── snapshots
    └── recordings

---

# Persistence Strategy

## Real-Time Data

The following data is processed in memory only and is never persisted:

- Video frames
- Object detections
- Tracking data
- Intermediate classifier outputs
- Distance estimation results
- Threat assessment results

Reason:

These are transient processing artifacts and would generate excessive storage volume with limited operational value.

---

## Persisted Data

The following data is persisted:

- Cameras
- Camera stream profiles
- Camera calibrations
- Incidents
- Incident events
- Snapshots
- Event clips
- System events
- Users

---

## Explicit Non-Persistence Rules

DO NOT STORE:

- Raw frames
- Frame-level metadata
- Detection history
- Tracking history
- Per-frame threat evaluations

STORE ONLY:

- Incident records
- Evidence (snapshots/clips)
- Threat metadata
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
Filesystem stores actual video and image files.