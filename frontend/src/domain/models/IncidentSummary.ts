/**
 * List-context companion to `Incident` (./Incident.ts). Mirrors
 * shared/schemas/incident.py::IncidentSummarySchema exactly -- the shape
 * `GET /incidents` and `GET /incidents/open` actually return (incident_id,
 * camera_id, threat_level, status, weapon_type; no track_id/incident_type/
 * uniform/zone/timestamps -- weapon_type is the one `threat_summary` field
 * included here too, since that's what an operator needs to triage the
 * list at a glance).
 *
 * This is a distinct type, not `Incident` with optional fields: fabricating
 * placeholder trackId/incidentType/timestamps to satisfy Incident's
 * constructor would be exactly the kind of invented data Phase 0's review
 * warned against. The incident list/grid uses `IncidentSummary`; selecting
 * a row and fetching `GET /incidents/{id}` upgrades to the full `Incident`
 * for the detail panel.
 */
import {
  canAcknowledgeIncident,
  canCloseIncident,
  isIncidentTerminal,
  type IncidentStatus,
} from "../incidentStatus";
import type { ThreatLevel } from "../threatLevel";

export class IncidentSummary {
  constructor(
    readonly id: string,
    readonly cameraId: string,
    readonly threatLevel: ThreatLevel,
    readonly status: IncidentStatus,
    readonly weaponType: string | null,
  ) {}

  canAcknowledge(): boolean {
    return canAcknowledgeIncident(this.status);
  }

  canClose(): boolean {
    return canCloseIncident(this.status);
  }

  isTerminal(): boolean {
    return isIncidentTerminal(this.status);
  }
}
