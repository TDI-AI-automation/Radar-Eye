# Radar Eye System Context

## External Actors

### Operator

Receives alerts.

Views live cameras.

Investigates incidents.

---

### Administrator

Configures system.

Manages users.

Reviews audit logs.

---

### Camera Network

Provides RTSP video streams.

---

### Alarm Devices

Receive alarm commands.

---

## System Boundary

Radar Eye Surveillance System

Responsibilities:

- Video ingestion
- AI inference
- Threat classification
- Alert generation
- Event recording
- Video retention
- Operator interface
- Administration interface

---

## High-Level Context

+----------------+
|   Operator     |
+----------------+
         |
         v
+-------------------------+
|        Radar Eye        |
+-------------------------+
         ^
         |
+----------------+
| Administrator  |
+----------------+

         ^

         |

+----------------+
| RTSP Cameras   |
+----------------+

         |

         v

+----------------+
| Radar Eye      |
+----------------+

         |

         v

+----------------+
| Alarm Devices  |
+----------------+