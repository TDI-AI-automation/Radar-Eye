/**
 * Incident domain model.
 *
 * Mirrors Radar-Eye backend's `Incident` (shared/constants/incident_types.py,
 * services/incident_service/service.py). This class owns *display/UI-affordance*
 * business logic only -- it is never the authority on whether a transition is
 * actually allowed. The backend re-validates every PATCH against
 * `IncidentService.request_transition()` regardless of what the UI shows; these
 * methods exist purely so components don't inline backend state-machine
 * knowledge directly in JSX.
 */

export type IncidentStatus = "NEW" | "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED" | "ARCHIVED";

export type ThreatLevel = "ALLY" | "OBSERVE" | "LOW" | "MEDIUM" | "HIGH" | "HUMAN_REVIEW";

export class Incident {
  constructor(
    readonly id: string,
    readonly cameraId: string,
    readonly trackId: number,
    readonly incidentType: string,
    readonly threatLevel: ThreatLevel,
    readonly status: IncidentStatus,
    readonly createdAt: Date,
    readonly updatedAt: Date,
  ) {}

  /**
   * Mirrors `EXTERNALLY_REQUESTABLE_TRANSITIONS` in
   * services/incident_service/service.py: ACTIVE -> ACKNOWLEDGED is the only
   * externally-requestable path into ACKNOWLEDGED.
   */
  canAcknowledge(): boolean {
    return this.status === "ACTIVE";
  }

  /**
   * Mirrors the same map: both ACTIVE -> RESOLVED (direct close) and
   * ACKNOWLEDGED -> RESOLVED are externally-requestable.
   */
  canClose(): boolean {
    return this.status === "ACTIVE" || this.status === "ACKNOWLEDGED";
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
    return this.status === "RESOLVED" || this.status === "ARCHIVED";
  }
}
