# Radar Eye Domain Model

## Core Entities

### Camera

Represents a video source.

Attributes:

- camera_id
- name
- location
- rtsp_url
- status

---

### Camera Calibration

Represents calibration parameters used for distance estimation.

Attributes:

- calibration_id
- camera_id
- mount_height
- tilt_angle
- ground_reference_points
- calibration_timestamp

---

### Video Stream

Represents decoded video frames from a camera.

Attributes:

- stream_id
- camera_id
- resolution
- fps
- codec

---

### Person Track

Represents a continuously tracked person across frames.

Attributes:

- track_id
- camera_id
- first_seen
- last_seen
- current_zone
- status

---

### Detection

Represents a model output.

Attributes:

- detection_id
- timestamp
- camera_id
- class
- confidence
- bounding_box

Possible Classes:

- person
- fire
- ranged_lethal
- melee_lethal
- non_lethal

---

### Uniform Classification

Represents classification of a tracked person.

Attributes:

- classification_id
- track_id
- classification
- confidence

Possible Values:

- Military
- Civilian
- Unknown

Military Definition:

- Green camouflage torso
- Green camouflage pants
- Black boots

Civilian Definition:

- Any other appearance

Unknown Definition:

- Confidence below threshold

---

### Threat Assessment

Represents threat evaluation for a tracked person.

Attributes:

- assessment_id
- track_id
- weapon_category
- zone
- threat_level

Weapon Categories:

- ranged_lethal
- melee_lethal
- non_lethal

Zones:

- Zone 1 (0–20m)
- Zone 2 (20–50m)
- Zone 3 (50m+)

Threat Levels:

- ALLY
- OBSERVE
- LOW
- MEDIUM
- HIGH

Threat Rules:

- Military + Any Weapon → ALLY
- Civilian + No Weapon → OBSERVE
- Fire → Separate Incident Pipeline

---

### Threat

Represents a classified security event.

Attributes:

- threat_id
- timestamp
- camera_id
- threat_type
- severity

---

### Incident

Represents a security incident.

Attributes:

- incident_id
- timestamp
- camera_id
- incident_type
- severity
- status

Incident Types:

- Human Threat
- Fire

---

### Alert

Represents an operator-facing notification.

Attributes:

- alert_id
- threat_id
- timestamp
- status

Current Delivery Channel:

- UI

Future Delivery Channels:

- SMS
- Email
- WhatsApp
- GPIO Relay
- Audio Siren

---

### Event

Represents a recorded system occurrence.

Attributes:

- event_id
- timestamp
- event_type

---

### Recording

Represents retained video.

Attributes:

- recording_id
- camera_id
- start_time
- end_time
- storage_location

---

### User

Represents a system user.

Attributes:

- user_id
- username
- role
- status

---

### Role

Represents RBAC permissions.

Attributes:

- role_id
- name

---

### Audit Log

Represents user and system actions.

Attributes:

- audit_id
- timestamp
- actor
- action