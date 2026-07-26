import type { IncidentSummary } from "@/domain/models/IncidentSummary";

export interface IncidentRowViewModel {
  id: string;
  cameraId: string;
  cameraName: string;
  threatLevel: IncidentSummary["threatLevel"];
  status: IncidentSummary["status"];
}

/**
 * IncidentSummarySchema (GET /incidents, GET /incidents/open) carries only
 * incident_id/camera_id/threat_level/status -- no weapon type, no
 * assigned-operator, no location, no timestamp. The prototype's incident
 * card showed all four (as "object"/"operator"/"location"/"time"); none
 * of those fields exist on the backend's Incident entity at all, so they
 * are not carried forward (docs/FRONTEND_ARCHITECTURE.md's Phase 2
 * checkpoint records this). Camera *name* is real, joined here from
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
  };
}
