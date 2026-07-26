import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type EvidenceItemDto = components["schemas"]["EvidenceItemSchema"];

export function listEvidence(): Promise<EvidenceItemDto[] | null> {
  return apiClient.request<EvidenceItemDto[]>("/evidence");
}

/** download_url (e.g. "/recordings/{id}/download") is server-provided on
 * every EvidenceItemSchema -- these endpoints return the raw file, not an
 * ApiResponse envelope (apps/api/app/routers/evidence.py returns
 * FileResponse directly), so requestBlob() is used, not request(). */
export function downloadEvidence(downloadUrl: string): Promise<Blob> {
  return apiClient.requestBlob(downloadUrl);
}
