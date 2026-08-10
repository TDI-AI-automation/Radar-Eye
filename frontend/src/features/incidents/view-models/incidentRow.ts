import type { IncidentSummary } from "@/domain/models/IncidentSummary";

export interface IncidentRowViewModel {
  id: string;
  cameraId: string;
  cameraName: string;
  threatLevel: IncidentSummary["threatLevel"];
  status: IncidentSummary["status"];
  weaponType: string | null;
}

/**
 * IncidentSummarySchema (GET /incidents, GET /incidents/open) carries
 * incident_id/camera_id/threat_level/status/weapon_type -- no assigned-
 * operator, no location, no timestamp. The prototype's incident card
 * showed all four (as "object"/"operator"/"location"/"time"); weapon type
 * ("object") is now real (ADR-029 Phase 5's classification wiring);
 * operator/location/timestamp still don't exist on the backend's Incident
 * entity, so they remain dropped, not fabricated
 * (docs/FRONTEND_ARCHITECTURE.md's Phase 2 checkpoint records the
 * original decision). Camera *name* is real, joined here from
 * GET /cameras the same way Analytics joins camera names onto incident
 * counts (queries/useCameras.ts).
 */
export function buildIncidentRowViewModel(
  incident: IncidentSummary,
  cameraName: string | undefined,
): IncidentRowViewModel {
  return {
    id: incident.id,
    cameraId: incident.cameraId,
    cameraName: cameraName ?? incident.cameraId,
    threatLevel: incident.threatLevel,
    status: incident.status,
    weaponType: incident.weaponType,
  };
}

export interface IncidentStatusCounts {
  open: number;
  acknowledged: number;
  resolved: number;
}

/** Same category of aggregation as features/analytics/view-models'
 * buildIncidentStatusCounts() -- kept here instead of inline in
 * routes/incidents.tsx for the same reason: display-count aggregation is
 * view-model work, not a route component's job. */
export function buildIncidentStatusCounts(incidents: IncidentSummary[]): IncidentStatusCounts {
  let open = 0;
  let acknowledged = 0;
  let resolved = 0;
  for (const i of incidents) {
    if (i.status === "NEW" || i.status === "ACTIVE") open += 1;
    if (i.status === "ACKNOWLEDGED") acknowledged += 1;
    if (i.status === "RESOLVED" || i.status === "ARCHIVED") resolved += 1;
  }
  return { open, acknowledged, resolved };
}
