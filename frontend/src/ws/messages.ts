import type { components } from "../api/generated/schema";

/**
 * WS message shapes -- hand-declared, NOT generated.
 *
 * FastAPI's OpenAPI schema only describes HTTP routes; WebSocket routes
 * (apps/api/app/websockets/routes.py) have no OpenAPI representation, so
 * openapi-typescript never sees them. This is a real gap in the "generated
 * types are the read-only source of truth" principle (docs/
 * FRONTEND_ARCHITECTURE.md) that applies everywhere else in this codebase
 * -- flagged explicitly here and in the Phase 1 checkpoint rather than
 * silently hand-typed as if it were no different from the REST layer.
 * These types must be kept in sync by hand against shared/schemas/*.py's
 * WS-specific classes (cited per type below) until/unless a WS schema
 * export mechanism exists.
 *
 * `/ws/threats`' ThreatAssessmentSchema has no REST-exposed twin, but
 * ActiveThreatSchema (GET /threats/active, in the generated schema) is
 * documented as "Extends ThreatAssessmentSchema with no additional fields
 * for now" (shared/schemas/threat.py) -- reused here rather than
 * duplicated by hand.
 */
export type ThreatAssessmentMessage = components["schemas"]["ActiveThreatSchema"];

/** shared/schemas/review.py::HumanReviewSchema -- also GET /reviews/{id}'s
 * response, so this one IS in the generated schema; reused, not hand-typed. */
export type ReviewMessage = components["schemas"]["HumanReviewSchema"];

/** shared/schemas/incident.py::IncidentCreatedSchema */
export interface IncidentCreatedMessage {
  incident_id: string;
  camera_id: string;
  track_id: number;
  status: components["schemas"]["IncidentStatus"];
}

/** shared/schemas/incident.py::IncidentUpdatedSchema */
export interface IncidentUpdatedMessage {
  incident_id: string;
  old_status: components["schemas"]["IncidentStatus"];
  new_status: components["schemas"]["IncidentStatus"];
}

export type IncidentMessage = IncidentCreatedMessage | IncidentUpdatedMessage;

/** shared/schemas/camera.py::CameraDisconnectedSchema */
export interface CameraDisconnectedMessage {
  camera_id: string;
  reason: string;
}

/** shared/schemas/camera.py::SystemEventSchema; severity from
 * shared/events/payloads.py::SystemEventSeverity. */
export interface SystemEventMessage {
  severity: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  source_component: string;
  message: string;
}

export type CameraHealthMessage = CameraDisconnectedMessage | SystemEventMessage;

/** shared/schemas/alarm.py::AlarmSchema */
export interface AlarmMessage {
  incident_id: string;
  camera_id: string;
  threat_level: components["schemas"]["ThreatLevel"];
}

/**
 * ConnectionManager.broadcast() sends the translated schema dict directly
 * (no envelope, no discriminator field -- apps/api/app/websockets/
 * bridge.py confirmed: `websocket.send_json(message)`, message is the
 * schema's own `.model_dump()`). Channels with a single message shape
 * need no discrimination; `incidents` and `camera_health` carry two
 * shapes each with no field to tell them apart except structurally.
 * These type guards are the one place that structural check lives.
 */
export function isIncidentUpdatedMessage(msg: IncidentMessage): msg is IncidentUpdatedMessage {
  return "old_status" in msg;
}

export function isSystemEventMessage(msg: CameraHealthMessage): msg is SystemEventMessage {
  return "severity" in msg;
}
