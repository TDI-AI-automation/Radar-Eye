import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type ActiveThreatDto = components["schemas"]["ActiveThreatSchema"];

export function listActiveThreats(): Promise<ActiveThreatDto[] | null> {
  return apiClient.request<ActiveThreatDto[]>("/threats/active");
}
