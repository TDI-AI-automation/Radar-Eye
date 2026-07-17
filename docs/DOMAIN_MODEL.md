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

### Video Stream

Represents decoded video frames from a camera.

Attributes:

- stream_id
- camera_id
- resolution
- fps
- codec

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

### Alert

Represents an operator-facing notification.

Attributes:

- alert_id
- threat_id
- timestamp
- status

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