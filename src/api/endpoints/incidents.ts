import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type IncidentSummaryDto = components["schemas"]["IncidentSummarySchema"];
type IncidentDto = components["schemas"]["IncidentSchema"];
type IncidentEventDto = components["schemas"]["IncidentEventSchema"];
type IncidentTransitionRequest = components["schemas"]["IncidentTransitionRequestSchema"];

export function listIncidents(): Promise<IncidentSummaryDto[] | null> {
  return apiClient.request<IncidentSummaryDto[]>("/incidents");
}

export function listOpenIncidents(): Promise<IncidentSummaryDto[] | null> {
  return apiClient.request<IncidentSummaryDto[]>("/incidents/open");
}

export function getIncident(incidentId: string): Promise<IncidentDto | null> {
  return apiClient.request<IncidentDto>(`/incidents/${incidentId}`);
}

export function getIncidentEvents(incidentId: string): Promise<IncidentEventDto[] | null> {
  return apiClient.request<IncidentEventDto[]>(`/incidents/${incidentId}/events`);
}

/** PATCH /incidents/{id} -- operator-gated on the backend
 * (require_role(ROLE_OPERATOR)); the only field a caller may request a
 * change to is `status`, and only via IncidentService.request_transition()'s
 * EXTERNALLY_REQUESTABLE_TRANSITIONS map (ACTIVE->ACKNOWLEDGED,
 * ACTIVE->RESOLVED, ACKNOWLEDGED->RESOLVED). The backend re-validates
 * regardless of what Incident.canAcknowledge()/canClose() show client-side. */
export function transitionIncident(
  incidentId: string,
  body: IncidentTransitionRequest,
): Promise<IncidentDto | null> {
  return apiClient.request<IncidentDto>(`/incidents/${incidentId}`, {
    method: "PATCH",
    body,
  });
}
