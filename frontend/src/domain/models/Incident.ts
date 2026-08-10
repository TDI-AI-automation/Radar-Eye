/**
 * Incident domain model.
 *
 * Mirrors Radar-Eye backend's `Incident` (shared/constants/incident_types.py,
 * services/incident_service/service.py) as returned in full by
 * `GET /incidents/{id}` (shared/schemas/incident.py::IncidentSchema). This
 * class owns *display/UI-affordance* business logic only -- it is never the
 * authority on whether a transition is actually allowed. The backend
 * re-validates every PATCH against `IncidentService.request_transition()`
 * regardless of what the UI shows; these methods exist purely so components
 * don't inline backend state-machine knowledge directly in JSX.
 *
 * For list contexts (`GET /incidents`, `GET /incidents/open`), the backend
 * returns the leaner `IncidentSummarySchema` (no track_id/incident_type/
 * timestamps) -- see `IncidentSummary` (./IncidentSummary.ts), which shares
 * this class's transition-check logic via ../incidentStatus.ts rather than
 * being constructed from partial/fabricated data.
 */
import {
  canAcknowledgeIncident,
  canCloseIncident,
  isIncidentTerminal,
  type IncidentStatus,
} from "../incidentStatus";
import type { ThreatLevel } from "../threatLevel";

export type { IncidentStatus };
export type { ThreatLevel };

export class Incident {
  constructor(
    readonly id: string,
    readonly cameraId: string,
    readonly trackId: number,
    readonly incidentType: string,
    readonly threatLevel: ThreatLevel,
    readonly status: IncidentStatus,
    readonly weaponType: string | null,
    readonly uniform: string | null,
    readonly zone: string | null,
    readonly createdAt: Date,
    readonly updatedAt: Date,
  ) {}

  canAcknowledge(): boolean {
    return canAcknowledgeIncident(this.status);
  }

  canClose(): boolean {
    return canCloseIncident(this.status);
  }

  /**
   * Deliberately NOT implemented as a real capability. The backend's
   * Incident state machine has no "escalate" transition for Incident itself
   * (NEW/ACTIVE are system-owned; ACKNOWLEDGED/RESOLVED are the only
   * externally-requestable targets; ARCHIVED is retention-service-only) --
   * "escalate" is a HumanReviewItem action (`POST /reviews/{id}/escalate`),
   * a distinct backend concept. Kept here, returning `false` unconditionally,
   * so a caller reads the absence of this capability explicitly rather than
   * the method being silently missing -- update this if/when product defines
   * a real escalate-an-incident capability backed by an actual endpoint.
   */
  canEscalate(): boolean {
    return false;
  }

  isTerminal(): boolean {
    return isIncidentTerminal(this.status);
  }
}
