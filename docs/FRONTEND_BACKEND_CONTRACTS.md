# Frontend Backend Contracts

---

# Live Monitoring

Frontend Requires:

GET /cameras

GET /incidents/open

GET /threats/active

WebSocket /events/threats

WebSocket /events/incidents

---

# Incident Center

Frontend Requires:

GET /incidents

GET /incidents/{incident_id}

PATCH /incidents/{incident_id}

GET /incidents/{incident_id}/evidence

---

# Tactical Map

Frontend Requires:

GET /cameras

GET /threats/active

GET /incidents/open

WebSocket /events/tracking

---

# Camera Management

Frontend Requires:

GET /cameras

GET /cameras/{camera_id}

PATCH /cameras/{camera_id}

GET /cameras/{camera_id}/health

---

# Analytics

Frontend Requires:

GET /analytics/threats

GET /analytics/incidents

GET /analytics/cameras

GET /analytics/system

---

# System Health

Frontend Requires:

GET /health/system

GET /health/gpu

GET /health/storage

GET /health/recording

---

# Settings

Frontend Requires:

GET /config

PATCH /config

GET /users

PATCH /users

---

# Threat Review Center

Frontend Requires:

GET /threats/pending

GET /threats/{threat_id}

PATCH /threats/{threat_id}

POST /threats/{threat_id}/escalate

---

# Calibration Center

Frontend Requires:

GET /calibration/cameras

POST /calibration/start

POST /calibration/validate

GET /calibration/results

---

# Evidence Viewer

Frontend Requires:

GET /evidence

GET /evidence/{evidence_id}

GET /recordings

GET /recordings/{recording_id}

---

# Event Streaming

The following shall be real-time:

- Threat Events
- Incident Events
- Camera Health Events
- System Health Events

Transport:

WebSocket

Polling shall be avoided where practical.