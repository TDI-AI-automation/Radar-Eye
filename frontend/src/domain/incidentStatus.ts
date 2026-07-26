/**
 * Canonical IncidentStatus type + backend-mirrored transition-check
 * predicates, extracted so both the full `Incident` domain model
 * (GET /incidents/{id}, all fields) and the list-context `IncidentSummary`
 * (GET /incidents, GET /incidents/open -- camera_id/threat_level/status
 * only, per shared/schemas/incident.py::IncidentSummarySchema) can share
 * the identical logic without duplicating it or requiring one to be
 * constructed from the other's incomplete data.
 *
 * Mirrors services/incident_service/service.py::
 * EXTERNALLY_REQUESTABLE_TRANSITIONS exactly -- display/UI-affordance
 * logic only, never the authority. The backend re-validates every PATCH
 * regardless of what these return.
 */
export type IncidentStatus = "NEW" | "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED" | "ARCHIVED";

/** ACTIVE -> ACKNOWLEDGED is the only externally-requestable path into
 * ACKNOWLEDGED. */
export function canAcknowledgeIncident(status: IncidentStatus): boolean {
  return status === "ACTIVE";
}

/** Both ACTIVE -> RESOLVED (direct close) and ACKNOWLEDGED -> RESOLVED are
 * externally-requestable. */
export function canCloseIncident(status: IncidentStatus): boolean {
  return status === "ACTIVE" || status === "ACKNOWLEDGED";
}

export function isIncidentTerminal(status: IncidentStatus): boolean {
  return status === "RESOLVED" || status === "ARCHIVED";
}
